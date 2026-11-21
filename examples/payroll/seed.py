"""Deterministic payroll data for demos, tests and the benchmark."""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date

from backdate import writes
from backdate.derive import worker
from backdate.intervals import Span
from backdate.writes import Assert

STATES = {"KA": 1_000, "MH": 1_200, "TN": 900, "DL": 1_100}


@dataclass(frozen=True, slots=True)
class Plan:
    employees: int
    year: int = 2024
    months: int = 12
    seed: int = 7


def employee_ops(rng: random.Random, emp: int, year: int) -> list[Assert]:
    hired = date(year, rng.randint(1, 3), rng.randint(1, 28))
    entity = f"employee:{emp}"
    salary = rng.randrange(40_000, 160_000, 500) * 100
    state = rng.choice(sorted(STATES))
    fte = rng.choice([10_000, 10_000, 10_000, 8_000, 5_000])
    return [
        Assert(entity, "annual_salary_cents", Span(hired), salary),
        Assert(entity, "fte_bp", Span(hired), fte),
        Assert(entity, "state", Span(hired), state),
    ]


def seed(tenant_id: int, plan: Plan, *, chunk: int = 150) -> list[str]:
    """Write rates and employees, request every month. Returns the keys."""
    rng = random.Random(plan.seed)  # noqa: S311 - demo data, needs to be reproducible
    rates = [
        Assert(f"taxrate:{s}", "withholding_bp", Span(date(plan.year, 1, 1)), bp)
        for s, bp in STATES.items()
    ]
    writes.apply(tenant_id, rates, reason="seed tax rates")
    ops: list[Assert] = []
    for emp in range(1, plan.employees + 1):
        ops.extend(employee_ops(rng, emp, plan.year))
        if len(ops) >= chunk:
            writes.apply(tenant_id, ops, reason="seed employees")
            ops = []
    if ops:
        writes.apply(tenant_id, ops, reason="seed employees")

    keys = [
        f"{emp}:{plan.year}-{m:02d}"
        for emp in range(1, plan.employees + 1)
        for m in range(1, plan.months + 1)
    ]
    for i in range(0, len(keys), 5000):
        worker.request(tenant_id, "payroll.gross", keys[i : i + 5000])
        worker.request(tenant_id, "payroll.withholding", keys[i : i + 5000])
    return keys
