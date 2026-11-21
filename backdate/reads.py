"""Bitemporal reads.

Every read is pinned to a knowledge version. Leave it out and you get the
latest committed version, read once at the start of the call. Because
versions commit in order (see ``backdate.clock``), the rows visible at
version N never change after N is visible, so the same call with the same
version always returns the same answer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from django.db.models import Q, QuerySet

from backdate.intervals import Span, coalesce
from backdate.models import Fact, TenantClock


@dataclass(frozen=True, slots=True)
class Piece:
    span: Span
    value: Any


@dataclass(frozen=True, slots=True)
class HistoryRow:
    span: Span
    value: Any
    tx_from: int
    tx_to: int | None


def committed_version(tenant_id: int) -> int:
    """Highest version whose writes are all committed.

    The clock row only shows a new version once the writer that bumped it
    commits, so this never returns a version that is still in flight.
    """
    row = TenantClock.objects.filter(tenant_id=tenant_id).values_list("version", flat=True).first()
    return row or 0


def known_at(version: int) -> Q:
    return Q(tx_from__lte=version) & (Q(tx_to__isnull=True) | Q(tx_to__gt=version))


def _facts(tenant_id: int, entity: str, attribute: str) -> QuerySet[Fact]:
    return Fact.objects.filter(tenant_id=tenant_id, entity=entity, attribute=attribute)


def timeline(
    tenant_id: int,
    entity: str,
    attribute: str,
    *,
    within: Span | None = None,
    version: int | None = None,
) -> list[Piece]:
    """Values of one attribute over valid time, as known at ``version``.

    Pieces are clipped to ``within`` and come back in canonical form: sorted,
    non-overlapping, and with no two touching pieces holding equal values.
    """
    v = committed_version(tenant_id) if version is None else version
    qs = _facts(tenant_id, entity, attribute).filter(known_at(v))
    if within is not None:
        qs = qs.filter(valid__overlap=within.to_range())
    pieces: list[tuple[Span, Any]] = []
    for valid, value in qs.values_list("valid", "value"):
        span = Span.from_range(valid)
        if within is not None:
            clipped = span.intersect(within)
            if clipped is None:
                continue
            span = clipped
        pieces.append((span, value))
    return [Piece(span, value) for span, value in coalesce(pieces)]


def value_at(
    tenant_id: int, entity: str, attribute: str, day: date, *, version: int | None = None
) -> Any | None:
    pieces = timeline(tenant_id, entity, attribute, within=Span.day(day), version=version)
    return pieces[0].value if pieces else None


def entity_at(
    tenant_id: int, entity: str, day: date, *, version: int | None = None
) -> dict[str, Any]:
    """Every attribute of an entity on one day."""
    v = committed_version(tenant_id) if version is None else version
    rows = (
        Fact.objects.filter(tenant_id=tenant_id, entity=entity)
        .filter(known_at(v))
        .filter(valid__contains=day)
        .values_list("attribute", "value")
    )
    return dict(rows)


def history(tenant_id: int, entity: str, attribute: str) -> list[HistoryRow]:
    """The full bitemporal record, including rows the system no longer believes."""
    rows = _facts(tenant_id, entity, attribute).order_by("tx_from", "valid")
    return [
        HistoryRow(Span.from_range(r.valid), r.value, r.tx_from, r.tx_to)
        for r in rows.only("valid", "value", "tx_from", "tx_to")
    ]
