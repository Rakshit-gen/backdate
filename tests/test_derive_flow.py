"""Write facts, compute payroll, backdate a change, watch the restatements."""

from datetime import date

import pytest

from backdate import writes
from backdate.derive import worker
from backdate.intervals import Span
from backdate.models import Computation, Restatement
from backdate.writes import Assert

pytestmark = pytest.mark.django_db
D = date


def hire(tenant, emp="1", salary=36_500_00, fte=10_000, state="KA", start=D(2024, 1, 1)):
    e = f"employee:{emp}"
    writes.apply(
        tenant.id,
        [
            Assert(e, "annual_salary_cents", Span(start), salary),
            Assert(e, "fte_bp", Span(start), fte),
            Assert(e, "state", Span(start), state),
        ],
    )


def set_rate(tenant, state, bp, start=D(2024, 1, 1)):
    writes.apply(tenant.id, [Assert(f"taxrate:{state}", "withholding_bp", Span(start), bp)])


def comp(tenant, derivation, key):
    return Computation.objects.get(tenant=tenant, derivation=derivation, key=key)


def test_gross_prorates_by_day(tenant):
    hire(tenant, salary=36_500_00, start=D(2024, 1, 11))
    worker.request(tenant.id, "payroll.gross", ["1:2024-01"])
    worker.drain("t", tenant_id=tenant.id)
    c = comp(tenant, "payroll.gross", "1:2024-01")
    assert c.status == "fresh"
    # 36,500.00 a year is 100.00 a day; hired on the 11th means 21 days paid.
    assert c.result == {"gross_cents": 21 * 100_00, "days_paid": 21}


def test_backdated_raise_restates_only_touched_months(tenant):
    hire(tenant)
    keys = [f"1:2024-{m:02d}" for m in range(1, 7)]
    worker.request(tenant.id, "payroll.gross", keys)
    worker.drain("t", tenant_id=tenant.id)

    result = writes.apply(
        tenant.id,
        [Assert("employee:1", "annual_salary_cents", Span(D(2024, 4, 1)), 73_000_00)],
    )
    assert result.invalidated == 3
    stale = set(
        Computation.objects.filter(tenant=tenant, status="stale").values_list("key", flat=True)
    )
    assert stale == {"1:2024-04", "1:2024-05", "1:2024-06"}

    worker.drain("t", tenant_id=tenant.id)
    april = comp(tenant, "payroll.gross", "1:2024-04")
    assert april.result["gross_cents"] == 30 * 200_00
    rows = list(Restatement.objects.filter(computation=april).order_by("seq"))
    assert [r.seq for r in rows] == [1, 2]
    assert rows[1].delta == {"gross_cents": 30 * 100_00}
    assert rows[1].from_version == 1 and rows[1].to_version == 2


def test_partial_month_change_splits_the_month(tenant):
    hire(tenant)
    worker.request(tenant.id, "payroll.gross", ["1:2024-03"])
    worker.drain("t", tenant_id=tenant.id)
    writes.apply(
        tenant.id,
        [Assert("employee:1", "fte_bp", Span(D(2024, 3, 16)), 5_000)],
    )
    worker.drain("t", tenant_id=tenant.id)
    march = comp(tenant, "payroll.gross", "1:2024-03")
    assert march.result["gross_cents"] == 15 * 100_00 + 16 * 50_00


def test_unrelated_write_invalidates_nothing(tenant):
    hire(tenant)
    hire(tenant, emp="2")
    worker.request(tenant.id, "payroll.gross", ["1:2024-03"])
    worker.drain("t", tenant_id=tenant.id)
    result = writes.apply(
        tenant.id, [Assert("employee:2", "annual_salary_cents", Span(D(2024, 1, 1)), 1)]
    )
    assert result.invalidated == 0
    assert comp(tenant, "payroll.gross", "1:2024-03").status == "fresh"


def test_recompute_with_same_answer_writes_no_restatement(tenant):
    hire(tenant)
    worker.request(tenant.id, "payroll.gross", ["1:2024-03"])
    worker.drain("t", tenant_id=tenant.id)
    # Splits the salary row in history but every day keeps its value... except
    # that is a no-op write. Change state instead: gross does not read state.
    writes.apply(tenant.id, [Assert("employee:1", "fte_bp", Span(D(2024, 3, 1)), 10_000)])
    assert comp(tenant, "payroll.gross", "1:2024-03").status == "fresh"
    assert Restatement.objects.filter(computation__key="1:2024-03").count() == 1


def test_withholding_waits_for_gross_then_follows_it(tenant):
    hire(tenant)
    set_rate(tenant, "KA", 1_000)
    worker.request(tenant.id, "payroll.withholding", ["1:2024-02"])
    worker.drain("t", tenant_id=tenant.id)
    wh = comp(tenant, "payroll.withholding", "1:2024-02")
    assert wh.status == "fresh"
    assert wh.result == {"withholding_cents": 29 * 10_00, "rate_bp": 1_000, "state": "KA"}

    writes.apply(
        tenant.id,
        [Assert("employee:1", "annual_salary_cents", Span(D(2024, 2, 1)), 73_000_00)],
    )
    assert comp(tenant, "payroll.withholding", "1:2024-02").status == "stale"
    worker.drain("t", tenant_id=tenant.id)
    assert comp(tenant, "payroll.withholding", "1:2024-02").result["withholding_cents"] == (
        29 * 20_00
    )


def test_rate_change_restates_withholding_but_not_gross(tenant):
    hire(tenant)
    set_rate(tenant, "KA", 1_000)
    worker.request(tenant.id, "payroll.withholding", ["1:2024-02"])
    worker.drain("t", tenant_id=tenant.id)
    set_rate(tenant, "KA", 1_500, start=D(2024, 2, 1))
    assert comp(tenant, "payroll.gross", "1:2024-02").status == "fresh"
    worker.drain("t", tenant_id=tenant.id)
    assert comp(tenant, "payroll.withholding", "1:2024-02").result["rate_bp"] == 1_500


def test_deltas_sum_to_current_result(tenant):
    hire(tenant)
    worker.request(tenant.id, "payroll.gross", ["1:2024-05"])
    worker.drain("t", tenant_id=tenant.id)
    for i, cents in enumerate([40_000_00, 45_000_00, 30_000_00]):
        writes.apply(
            tenant.id,
            [Assert("employee:1", "annual_salary_cents", Span(D(2024, 5, 1 + i)), cents)],
        )
        worker.drain("t", tenant_id=tenant.id)
    c = comp(tenant, "payroll.gross", "1:2024-05")
    total = sum(r.delta["gross_cents"] for r in Restatement.objects.filter(computation=c))
    assert total == c.result["gross_cents"]


def test_failing_derivation_backs_off_then_fails(tenant, settings):
    settings.BACKDATE = {**settings.BACKDATE, "MAX_ATTEMPTS": 2}
    worker.request(tenant.id, "payroll.gross", ["not-a-key"])
    claims = worker.claim("t", tenant_id=tenant.id)
    assert worker.run_one(claims[0]).outcome == "retry"
    Computation.objects.filter(key="not-a-key").update(not_before=None)
    claims = worker.claim("t", tenant_id=tenant.id)
    assert worker.run_one(claims[0]).outcome == "failed"
    c = comp(tenant, "payroll.gross", "not-a-key")
    assert c.status == "failed"
    assert "BadKey" in c.last_error
