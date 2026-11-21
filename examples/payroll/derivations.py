"""Payroll derivations.

Money is integer cents, rates are integer basis points, and rounding happens
once per result with banker's rounding, so recomputing a month always gives
the same number.
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from backdate.derive.context import Context
from backdate.derive.registry import derivation
from backdate.intervals import Span

DAYS_PER_YEAR = Decimal(365)
FULL_TIME_BP = Decimal(10_000)


class BadKey(ValueError):
    pass


def parse_key(key: str) -> tuple[str, Span]:
    """``"<employee_id>:<YYYY-MM>"`` to the employee entity and the month."""
    try:
        employee_id, month = key.split(":")
        year, mon = (int(part) for part in month.split("-"))
        calendar.monthrange(year, mon)  # rejects month 13 and friends
    except ValueError as exc:
        raise BadKey(f"expected '<employee>:<YYYY-MM>', got {key!r}") from exc
    if not employee_id:
        raise BadKey("empty employee id")
    start = date(year, mon, 1)
    end = date(year + (mon == 12), mon % 12 + 1, 1)
    return f"employee:{employee_id}", Span(start, end)


def employee_entity(employee_id: str | int) -> str:
    return f"employee:{employee_id}"


def taxrate_entity(state: str) -> str:
    return f"taxrate:{state}"


@derivation("payroll.gross", version="1")
def gross(ctx: Context, key: str) -> dict[str, Any]:
    """Gross pay for one employee and month, prorated by day and FTE."""
    entity, month = parse_key(key)
    salary = ctx.timeline(entity, "annual_salary_cents", month)
    fte = ctx.timeline(entity, "fte_bp", month)

    total = Decimal(0)
    days_paid = 0
    for day in month.iter_days():
        annual = _on(salary, day)
        share = _on(fte, day)
        if annual is None or share is None:
            continue
        days_paid += 1
        total += Decimal(annual) / DAYS_PER_YEAR * Decimal(share) / FULL_TIME_BP
    cents = int(total.quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
    return {"gross_cents": cents, "days_paid": days_paid}


@derivation("payroll.withholding", version="1")
def withholding(ctx: Context, key: str) -> dict[str, Any]:
    """Withholding for a month, at the rate of the state on the last day."""
    entity, month = parse_key(key)
    assert month.end is not None  # noqa: S101
    gross_result = ctx.derived("payroll.gross", key)
    last_day = date.fromordinal(month.end.toordinal() - 1)
    state = ctx.value_at(entity, "state", last_day)
    rate_bp = ctx.value_at(taxrate_entity(state), "withholding_bp", last_day) if state else None
    rate = Decimal(rate_bp or 0)
    held = Decimal(gross_result["gross_cents"]) * rate / FULL_TIME_BP
    return {
        "withholding_cents": int(held.quantize(Decimal(1), rounding=ROUND_HALF_EVEN)),
        "rate_bp": int(rate),
        "state": state,
    }


def _on(pieces: list[Any], day: date) -> Any | None:
    for piece in pieces:
        if piece.span.contains(day):
            return piece.value
    return None
