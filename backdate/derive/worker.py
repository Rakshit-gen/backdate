"""Claiming and running computations.

Workers are separate processes. They share nothing except Postgres:

* ``claim`` picks runnable rows with FOR UPDATE SKIP LOCKED, so two workers
  never pick the same row, and stamps each with a lease and a new fencing
  token. The claim commits right away; no lock is held while computing.
* ``run_one`` computes outside any transaction, then hands off to
  ``backdate.derive.save``.
* A worker that dies mid-compute leaves a lease that expires. Another worker
  can then claim the row, which bumps the token, so if the first worker
  wakes up and tries to save, the save is fenced off.
"""

from __future__ import annotations

import logging
import time
import traceback
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import connection, transaction
from django.db.models.expressions import RawSQL

from backdate import reads
from backdate.derive import registry
from backdate.derive.context import Context, NotReady
from backdate.derive.save import Claim, SaveOutcome, save
from backdate.models import Computation
from backdate.observability import metrics

log = logging.getLogger("backdate.worker")

_CLAIM_SQL = """
UPDATE backdate_computation c
   SET lease_owner = %(owner)s,
       lease_token = c.lease_token + 1,
       lease_expires_at = clock_timestamp() + make_interval(secs => %(lease)s),
       attempts = c.attempts + 1,
       updated_at = now()
 WHERE c.id IN (
       SELECT id FROM backdate_computation
        WHERE status IN ('pending', 'stale')
          AND (not_before IS NULL OR not_before <= clock_timestamp())
          AND (lease_expires_at IS NULL OR lease_expires_at < clock_timestamp())
          {tenant_filter}
        ORDER BY not_before NULLS FIRST, id
        LIMIT %(limit)s
        FOR UPDATE SKIP LOCKED)
RETURNING c.id, c.tenant_id, c.derivation, c.key, c.lease_token, c.attempts
"""


def claim(owner: str, limit: int = 10, tenant_id: int | None = None) -> list[Claim]:
    sql = _CLAIM_SQL.format(tenant_filter="AND tenant_id = %(tenant)s" if tenant_id else "")
    with transaction.atomic(), connection.cursor() as cur:
        cur.execute(
            sql,
            {
                "owner": owner,
                "lease": settings.BACKDATE["LEASE_SECONDS"],
                "limit": limit,
                "tenant": tenant_id,
            },
        )
        rows = cur.fetchall()
    return [Claim(*row) for row in rows]


@dataclass(frozen=True, slots=True)
class RunResult:
    claim: Claim
    outcome: str
    duration_ms: float


def run_one(claim: Claim) -> RunResult:
    started = time.perf_counter()
    outcome = _run(claim)
    elapsed = (time.perf_counter() - started) * 1000
    log.info(
        "computed",
        extra={
            "computation_id": claim.computation_id,
            "derivation": claim.derivation,
            "key": claim.key,
            "outcome": outcome,
            "duration_ms": round(elapsed, 2),
        },
    )
    metrics.computations.labels(claim.derivation, outcome).inc()
    metrics.compute_seconds.labels(claim.derivation).observe(elapsed / 1000)
    return RunResult(claim, outcome, elapsed)


def _run(claim: Claim) -> str:
    try:
        derivation = registry.get(claim.derivation)
    except registry.UnknownDerivation:
        return _fail(claim, f"no derivation named {claim.derivation!r}", permanent=True)

    ctx = Context(tenant_id=claim.tenant_id, version=reads.committed_version(claim.tenant_id))
    try:
        result = derivation.fn(ctx, claim.key)
    except NotReady as wait:
        request(claim.tenant_id, wait.derivation, [wait.key])
        return _wait(claim)
    except Exception as exc:  # a bug in a derivation must not kill the worker
        detail = "".join(traceback.format_exception_only(exc)).strip()
        return _fail(claim, detail)
    return save(claim, ctx, result, derivation.version).value


def _owned(claim: Claim) -> Computation | None:
    comp = Computation.objects.select_for_update().get(id=claim.computation_id)
    return comp if comp.lease_token == claim.token else None


def _wait(claim: Claim) -> str:
    with transaction.atomic():
        comp = _owned(claim)
        if comp is None:
            return SaveOutcome.FENCED.value
        comp.attempts = max(comp.attempts - 1, 0)
        comp.not_before = db_now_plus(timedelta(milliseconds=200))
        comp.lease_owner = ""
        comp.lease_expires_at = None
        comp.save()
    return "waiting"


def _fail(claim: Claim, error: str, *, permanent: bool = False) -> str:
    with transaction.atomic():
        comp = _owned(claim)
        if comp is None:
            return SaveOutcome.FENCED.value
        comp.last_error = error[:4000]
        comp.lease_owner = ""
        comp.lease_expires_at = None
        if permanent or comp.attempts >= settings.BACKDATE["MAX_ATTEMPTS"]:
            comp.status = Computation.Status.FAILED
            comp.not_before = None
            outcome = "failed"
        else:
            comp.not_before = db_now_plus(backoff(comp.attempts))
            outcome = "retry"
        comp.save()
    return outcome


def db_now_plus(delay: timedelta) -> RawSQL:
    # Database time, not app time: the claim query compares against the
    # database clock, and app hosts can drift. clock_timestamp() rather than
    # now() because now() is frozen at the start of the transaction.
    return RawSQL("clock_timestamp() + make_interval(secs => %s)", [delay.total_seconds()])


def backoff(attempts: int) -> timedelta:
    """1s, 2s, 4s, ... capped at 5 minutes."""
    return timedelta(seconds=min(2 ** max(attempts - 1, 0), 300))


def request(tenant_id: int, derivation: str, keys: Iterable[str]) -> int:
    """Make sure each (derivation, key) exists. New ones start pending.

    Returns how many were created. Existing rows are left alone, whatever
    their state.
    """
    registry.get(derivation)
    unique = sorted(set(keys))
    if not unique:
        return 0
    # bulk_create(ignore_conflicts=True) cannot say which rows were new.
    with connection.cursor() as cur:
        cur.execute(
            """
            INSERT INTO backdate_computation
                (tenant_id, derivation, key, status, code_version, result_seq, attempts,
                 last_error, lease_owner, lease_token, created_at, updated_at)
            SELECT %s, %s, k, 'pending', '', 0, 0, '', '', 0, now(), now()
              FROM unnest(%s::text[]) AS k
            ON CONFLICT (tenant_id, derivation, key) DO NOTHING
            """,
            [tenant_id, derivation, unique],
        )
        return cur.rowcount


def drain(
    owner: str, *, tenant_id: int | None = None, batch: int = 20, max_rounds: int = 1000
) -> int:
    """Run until nothing is runnable. Used by tests, the bench and ``--once``."""
    done = 0
    for _ in range(max_rounds):
        claims = claim(owner, batch, tenant_id)
        if not claims:
            if not _has_delayed(tenant_id):
                return done
            time.sleep(0.05)
            continue
        for c in claims:
            run_one(c)
            done += 1
    return done


def _has_delayed(tenant_id: int | None) -> bool:
    qs = Computation.objects.filter(
        status__in=[Computation.Status.PENDING, Computation.Status.STALE]
    )
    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)
    return qs.exists()
