"""Saving a computed result without losing an invalidation.

The race this guards against:

    worker reads facts at version 7, computes R
    writer commits version 8, which changes a fact the worker read
        -> writer marks fresh results stale, but this one is not fresh yet
    worker saves R as fresh at version 7
        -> R is wrong and nothing will ever recompute it

The save closes the gap in three steps, all in one transaction:

1. Take the tenant clock FOR SHARE. This waits for any writer still holding
   the clock, so every write that will ever get a version at or below the
   current clock value has committed by the time the lock is granted.
2. Lock the computation row and check the fencing token. A worker whose
   lease expired and was handed to someone else gets ``Fenced`` and writes
   nothing.
3. Look for any ``ChangeRange`` newer than the version the worker read at
   that overlaps something it read. If one exists, the result is already
   out of date. Put it back in the queue instead of saving it.

Writers need the clock FOR UPDATE, which conflicts with the share lock,
so no write can start or commit while a save is in progress. Any write
that commits after the save sees the new read ranges and a result_version
below its own version, and marks the result stale the normal way.

Dependencies on other derived results work the same way, with ``result_seq``
in place of the version: the saver takes each source FOR SHARE and checks
the seq it observed is still the current one.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from numbers import Number
from typing import Any

from django.db import connection, transaction
from django.db.models import Q

from backdate import clock
from backdate.derive.context import Context
from backdate.intervals import Span
from backdate.models import ChangeRange, Computation, DerivedRead, ReadRange, Restatement


class SaveOutcome(enum.Enum):
    SAVED = "saved"
    UNCHANGED = "unchanged"
    REQUEUED = "requeued"
    FENCED = "fenced"


@dataclass(frozen=True, slots=True)
class Claim:
    computation_id: int
    tenant_id: int
    derivation: str
    key: str
    token: int
    attempts: int


def save(claim: Claim, ctx: Context, result: Any, code_version: str) -> SaveOutcome:
    read_set = ctx.read_set()
    with transaction.atomic():
        clock.share_lock(claim.tenant_id)
        comp = Computation.objects.select_for_update().get(id=claim.computation_id)
        if comp.lease_token != claim.token:
            return SaveOutcome.FENCED

        if _moved_since(claim.tenant_id, ctx.version, read_set) or not _sources_current(ctx):
            _requeue(comp)
            return SaveOutcome.REQUEUED

        changed = comp.result_seq == 0 or comp.result != result
        if changed:
            comp.result_seq += 1
            Restatement.objects.create(
                tenant_id=claim.tenant_id,
                computation=comp,
                seq=comp.result_seq,
                from_version=comp.result_version,
                to_version=ctx.version,
                previous=comp.result if comp.result_seq > 1 else None,
                current=result,
                delta=delta(comp.result if comp.result_seq > 1 else None, result),
            )
        comp.result = result
        comp.result_version = ctx.version
        comp.code_version = code_version
        comp.status = Computation.Status.FRESH
        comp.stale_since_version = None
        comp.attempts = 0
        comp.last_error = ""
        comp.not_before = None
        _clear_lease(comp)
        comp.save()

        ReadRange.objects.filter(computation=comp).delete()
        ReadRange.objects.bulk_create(
            ReadRange(
                tenant_id=claim.tenant_id,
                computation=comp,
                entity=entity,
                attribute=attribute,
                valid=span.to_range(),
            )
            for entity, attribute, span in read_set
        )
        DerivedRead.objects.filter(reader=comp).delete()
        DerivedRead.objects.bulk_create(
            DerivedRead(reader=comp, source_id=obs.computation_id, observed_seq=obs.seq)
            for obs in ctx.derived_reads()
        )
        if changed and comp.result_seq > 1:
            mark_dependents_stale(comp.id, ctx.version)
        return SaveOutcome.SAVED if changed else SaveOutcome.UNCHANGED


def _moved_since(tenant_id: int, version: int, read_set: list[tuple[str, str, Span]]) -> bool:
    if not read_set:
        return False
    overlap = Q()
    for entity, attribute, span in read_set:
        overlap |= Q(entity=entity, attribute=attribute, valid__overlap=span.to_range())
    newer = ChangeRange.objects.filter(tenant_id=tenant_id, version__gt=version)
    return newer.filter(overlap).exists()


def _sources_current(ctx: Context) -> bool:
    observed = ctx.derived_reads()
    if not observed:
        return True
    ids = sorted(obs.computation_id for obs in observed)
    # Django has no FOR SHARE. A share lock is what we want: it waits for a
    # source that is mid-save, and lets other dependents check it in parallel.
    with connection.cursor() as cur:
        cur.execute(
            "SELECT id, result_seq FROM backdate_computation"
            " WHERE id = ANY(%s) AND status = 'fresh' ORDER BY id FOR SHARE",
            [ids],
        )
        current = dict(cur.fetchall())
    return all(current.get(obs.computation_id) == obs.seq for obs in observed)


def _requeue(comp: Computation) -> None:
    comp.status = Computation.Status.STALE if comp.result_seq else Computation.Status.PENDING
    comp.not_before = None
    # Losing a race is not the derivation's fault.
    comp.attempts = max(comp.attempts - 1, 0)
    _clear_lease(comp)
    comp.save()


def _clear_lease(comp: Computation) -> None:
    comp.lease_owner = ""
    comp.lease_expires_at = None


def mark_dependents_stale(source_id: int, version: int) -> int:
    """Mark results that used ``source_id`` stale.

    SKIP LOCKED because a dependent whose row is locked is in the middle of
    its own save, and that save re-checks this source's seq under a share
    lock, so it will notice the change and requeue itself. Waiting here
    instead could deadlock against it.
    """
    with connection.cursor() as cur:
        cur.execute(
            """
            UPDATE backdate_computation c
               SET status = 'stale',
                   stale_since_version = COALESCE(c.stale_since_version, %s),
                   updated_at = now()
             WHERE c.id IN (
                   SELECT c2.id FROM backdate_computation c2
                     JOIN backdate_derivedread d ON d.reader_id = c2.id
                    WHERE d.source_id = %s AND c2.status = 'fresh'
                    FOR UPDATE OF c2 SKIP LOCKED)
            """,
            [version, source_id],
        )
        return cur.rowcount


def delta(previous: Any, current: Any) -> Any:
    """Numeric difference between two results, field by field.

    Only numbers get a delta. Summing the deltas of every restatement of a
    computation gives the numeric fields of its current result, which is
    what a ledger downstream wants to post.
    """
    if _is_number(current):
        return current - (previous if _is_number(previous) else 0)
    if isinstance(current, dict):
        prev = previous if isinstance(previous, dict) else {}
        out: dict[str, Any] = {}
        for k, v in current.items():
            if _is_number(v):
                d = v - (prev.get(k) if _is_number(prev.get(k)) else 0)
                if d or previous is None:
                    out[k] = d
        for k, v in prev.items():
            if _is_number(v) and not _is_number(current.get(k)):
                out[k] = -v
        return out
    return {}


def _is_number(v: Any) -> bool:
    return isinstance(v, Number) and not isinstance(v, bool)
