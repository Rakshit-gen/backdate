"""The write path.

A write is a list of operations, each saying what an attribute's value is
(or is not) over some valid-time span. They are applied in one transaction:

1. Lock the tenant clock (serializes writers in the tenant).
2. For each touched (entity, attribute), load the current rows, apply the
   operations in memory with ``backdate.timeline`` and diff old against new.
3. If nothing changed, stop. No version is spent and nothing is invalidated,
   so retrying a write that already landed is cheap and harmless.
4. Otherwise bump the version, close the rows that are no longer true,
   insert the new ones, record which valid-time spans changed, and mark
   every fresh result that read any of those spans stale.

Because step 4 runs in the same transaction as the fact change, a reader can
never see the new facts next to a result that still claims to be fresh for
the old ones.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from django.db import connection, transaction

from backdate import clock, conf
from backdate.intervals import Span, parse_span
from backdate.models import ChangeRange, Changeset, Fact, IdempotencyRecord
from backdate.timeline import Timeline, assert_value, changed_spans, retract


class WriteError(ValueError):
    pass


class IdempotencyConflict(WriteError):
    """Same idempotency key, different request body."""


@dataclass(frozen=True, slots=True)
class Assert:
    entity: str
    attribute: str
    span: Span
    value: Any


@dataclass(frozen=True, slots=True)
class Retract:
    entity: str
    attribute: str
    span: Span


Op = Assert | Retract


@dataclass(frozen=True, slots=True)
class Change:
    entity: str
    attribute: str
    span: Span


@dataclass
class WriteResult:
    version: int
    changes: list[Change] = field(default_factory=list)
    invalidated: int = 0
    replayed: bool = False

    @property
    def noop(self) -> bool:
        return not self.changes

    def as_json(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "noop": self.noop,
            "invalidated": self.invalidated,
            "changes": [
                {
                    "entity": c.entity,
                    "attribute": c.attribute,
                    "start": c.span.start.isoformat(),
                    "end": c.span.end.isoformat() if c.span.end else None,
                }
                for c in self.changes
            ],
        }


def apply(
    tenant_id: int,
    ops: Sequence[Op],
    *,
    actor: str = "",
    reason: str = "",
    idempotency_key: str | None = None,
    request_hash: str = "",
) -> WriteResult:
    _validate(ops)
    with transaction.atomic():
        base = clock.lock_for_write(tenant_id)

        # Writers in a tenant are serialized by the clock lock, so a plain
        # lookup here cannot race with another request using the same key.
        if idempotency_key is not None:
            replay = _replay(tenant_id, idempotency_key, request_hash)
            if replay is not None:
                return replay

        plans = _plan(tenant_id, ops)
        if not plans:
            result = WriteResult(version=base)
        else:
            version = clock.advance(tenant_id, base)
            changeset = Changeset.objects.create(
                tenant_id=tenant_id,
                version=version,
                actor=actor,
                reason=reason,
                idempotency_key=idempotency_key or "",
            )
            changes = _persist(tenant_id, changeset, plans)
            invalidated = invalidate(tenant_id, version, changes)
            result = WriteResult(version=version, changes=changes, invalidated=invalidated)

        if idempotency_key is not None:
            IdempotencyRecord.objects.create(
                tenant_id=tenant_id,
                key=idempotency_key,
                request_hash=request_hash,
                status_code=200,
                response=result.as_json(),
            )
        return result


def _validate(ops: Sequence[Op]) -> None:
    if not ops:
        raise WriteError("a write needs at least one operation")
    limit = conf.get_int("MAX_OPS_PER_CHANGESET")
    if len(ops) > limit:
        raise WriteError(f"at most {limit} operations per write, got {len(ops)}")
    for op in ops:
        if not op.entity or not op.attribute:
            raise WriteError("entity and attribute must be non-empty")
        if len(op.entity) > 200 or len(op.attribute) > 100:
            raise WriteError("entity or attribute name too long")


def _replay(tenant_id: int, key: str, request_hash: str) -> WriteResult | None:
    record = IdempotencyRecord.objects.filter(tenant_id=tenant_id, key=key).first()
    if record is None:
        return None
    if record.request_hash != request_hash:
        raise IdempotencyConflict(f"idempotency key {key!r} was used with a different body")
    body = record.response
    changes = [
        Change(c["entity"], c["attribute"], parse_span(c["start"], c["end"]))
        for c in body["changes"]
    ]
    return WriteResult(
        version=body["version"], changes=changes, invalidated=body["invalidated"], replayed=True
    )


@dataclass
class _Plan:
    entity: str
    attribute: str
    close_ids: list[int]
    insert: Timeline
    changed: list[Span]


def _plan(tenant_id: int, ops: Sequence[Op]) -> list[_Plan]:
    grouped: dict[tuple[str, str], list[Op]] = {}
    for op in ops:
        grouped.setdefault((op.entity, op.attribute), []).append(op)

    plans: list[_Plan] = []
    for (entity, attribute), group in grouped.items():
        rows = list(
            Fact.objects.filter(
                tenant_id=tenant_id, entity=entity, attribute=attribute, tx_to__isnull=True
            ).values_list("id", "valid", "value")
        )
        before = [(Span.from_range(valid), value) for _, valid, value in rows]
        after: Timeline = sorted(before, key=lambda p: p[0].start)
        for op in group:
            if isinstance(op, Assert):
                after = assert_value(after, op.span, op.value)
            else:
                after = retract(after, op.span)

        changed = changed_spans(before, after)
        if not changed:
            continue
        # Keep rows that survive unchanged, close the rest, insert what is new.
        # Comparing (span, value) pairs keeps history free of rows that were
        # closed and reinserted with identical content.
        after_set = {(span, _freeze(value)) for span, value in after}
        before_set = {(span, _freeze(value)) for span, value in before}
        close_ids = [
            row_id
            for (row_id, _, _), (span, value) in zip(rows, before, strict=True)
            if (span, _freeze(value)) not in after_set
        ]
        insert = [(s, v) for s, v in after if (s, _freeze(v)) not in before_set]
        plans.append(_Plan(entity, attribute, close_ids, insert, changed))
    return plans


def _freeze(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _persist(tenant_id: int, changeset: Changeset, plans: list[_Plan]) -> list[Change]:
    version = changeset.version
    close_ids = [row_id for plan in plans for row_id in plan.close_ids]
    if close_ids:
        Fact.objects.filter(id__in=close_ids).update(tx_to=version)
    Fact.objects.bulk_create(
        Fact(
            tenant_id=tenant_id,
            entity=plan.entity,
            attribute=plan.attribute,
            value=value,
            valid=span.to_range(),
            tx_from=version,
            changeset=changeset,
        )
        for plan in plans
        for span, value in plan.insert
    )
    changes = [Change(p.entity, p.attribute, span) for p in plans for span in p.changed]
    ChangeRange.objects.bulk_create(
        ChangeRange(
            tenant_id=tenant_id,
            changeset=changeset,
            version=version,
            entity=c.entity,
            attribute=c.attribute,
            valid=c.span.to_range(),
        )
        for c in changes
    )
    return changes


_INVALIDATE_SQL = """
WITH RECURSIVE changed AS (
    SELECT * FROM unnest(%(entities)s::text[], %(attributes)s::text[], %(ranges)s::daterange[])
        AS t(entity, attribute, valid)
),
direct AS (
    SELECT DISTINCT r.computation_id AS id
    FROM backdate_readrange r
    JOIN changed ch
      ON r.tenant_id = %(tenant)s
     AND r.entity = ch.entity
     AND r.attribute = ch.attribute
     AND r.valid && ch.valid
),
affected(id) AS (
    -- Results built on top of an affected result are affected too.
    SELECT id FROM direct
    UNION
    SELECT d.reader_id FROM backdate_derivedread d JOIN affected a ON d.source_id = a.id
)
UPDATE backdate_computation c
   SET status = 'stale',
       stale_since_version = COALESCE(c.stale_since_version, %(version)s),
       attempts = CASE WHEN c.status = 'failed' THEN 0 ELSE c.attempts END,
       not_before = NULL,
       updated_at = now()
  FROM affected a
 WHERE c.id = a.id
   AND c.tenant_id = %(tenant)s
   AND c.status IN ('fresh', 'failed')
   AND (c.result_version IS NULL OR c.result_version < %(version)s)
"""


def invalidate(tenant_id: int, version: int, changes: Sequence[Change]) -> int:
    """Mark results that read any changed span stale. Returns how many."""
    if not changes:
        return 0
    with connection.cursor() as cur:
        cur.execute(
            _INVALIDATE_SQL,
            {
                "tenant": tenant_id,
                "version": version,
                "entities": [c.entity for c in changes],
                "attributes": [c.attribute for c in changes],
                "ranges": [_range_literal(c.span) for c in changes],
            },
        )
        return int(cur.rowcount)


def _range_literal(span: Span) -> str:
    end = span.end.isoformat() if span.end else ""
    return f"[{span.start.isoformat()},{end})"
