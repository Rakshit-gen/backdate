"""The interleavings the save protocol exists for, driven step by step."""

from datetime import UTC, date, datetime

import pytest

from backdate import reads, writes
from backdate.derive import registry, worker
from backdate.derive.context import Context
from backdate.derive.save import SaveOutcome, save
from backdate.intervals import Span
from backdate.models import Computation, Restatement
from backdate.writes import Assert

pytestmark = pytest.mark.django_db
D = date
LONG_AGO = datetime(2000, 1, 1, tzinfo=UTC)


def seed(tenant):
    writes.apply(
        tenant.id,
        [
            Assert("employee:1", "annual_salary_cents", Span(D(2024, 1, 1)), 36_500_00),
            Assert("employee:1", "fte_bp", Span(D(2024, 1, 1)), 10_000),
        ],
    )
    worker.request(tenant.id, "payroll.gross", ["1:2024-03"])


def compute(claim):
    ctx = Context(claim.tenant_id, reads.committed_version(claim.tenant_id))
    return ctx, registry.get(claim.derivation).fn(ctx, claim.key)


def test_write_between_compute_and_save_forces_requeue(tenant):
    seed(tenant)
    (claim,) = worker.claim("w1", tenant_id=tenant.id)
    ctx, result = compute(claim)

    # A raise lands while the worker holds a result computed at the old version.
    writes.apply(tenant.id, [Assert("employee:1", "annual_salary_cents", Span(D(2024, 3, 10)), 1)])

    assert save(claim, ctx, result, "1") is SaveOutcome.REQUEUED
    c = Computation.objects.get(key="1:2024-03")
    assert c.status == "pending"
    assert c.result is None
    assert Restatement.objects.count() == 0

    worker.drain("w1", tenant_id=tenant.id)
    c.refresh_from_db()
    assert c.status == "fresh"
    assert c.result_version == 2


def test_write_outside_read_set_does_not_requeue(tenant):
    seed(tenant)
    (claim,) = worker.claim("w1", tenant_id=tenant.id)
    ctx, result = compute(claim)
    writes.apply(tenant.id, [Assert("employee:1", "annual_salary_cents", Span(D(2024, 5, 1)), 1)])
    assert save(claim, ctx, result, "1") is SaveOutcome.SAVED


def test_write_after_save_marks_stale(tenant):
    seed(tenant)
    worker.drain("w1", tenant_id=tenant.id)
    result = writes.apply(tenant.id, [Assert("employee:1", "fte_bp", Span(D(2024, 3, 31)), 5_000)])
    assert result.invalidated == 1


def test_expired_lease_is_fenced_off(tenant):
    seed(tenant)
    (slow,) = worker.claim("slow", tenant_id=tenant.id)
    ctx, _ = compute(slow)

    Computation.objects.filter(id=slow.computation_id).update(lease_expires_at=LONG_AGO)
    (fast,) = worker.claim("fast", tenant_id=tenant.id)
    assert fast.token == slow.token + 1

    assert worker.run_one(fast).outcome == "saved"
    assert save(slow, ctx, {"gross_cents": -1}, "1") is SaveOutcome.FENCED
    c = Computation.objects.get(id=slow.computation_id)
    assert c.result["gross_cents"] == 31 * 100_00


def test_live_lease_is_not_claimed_twice(tenant):
    seed(tenant)
    assert len(worker.claim("a", tenant_id=tenant.id)) == 1
    assert worker.claim("b", tenant_id=tenant.id) == []


def test_fenced_worker_cannot_record_failure(tenant):
    seed(tenant)
    (old,) = worker.claim("old", tenant_id=tenant.id)
    Computation.objects.filter(id=old.computation_id).update(lease_expires_at=LONG_AGO)
    worker.claim("new", tenant_id=tenant.id)
    assert worker._fail(old, "boom") == "fenced"
    assert Computation.objects.get(id=old.computation_id).last_error == ""


def test_dependent_save_rejected_when_source_moved(tenant):
    seed(tenant)
    writes.apply(tenant.id, [Assert("employee:1", "state", Span(D(2024, 1, 1)), "KA")])
    writes.apply(tenant.id, [Assert("taxrate:KA", "withholding_bp", Span(D(2024, 1, 1)), 1000)])
    worker.drain("w", tenant_id=tenant.id)
    worker.request(tenant.id, "payroll.withholding", ["1:2024-03"])
    (claim,) = worker.claim("w", tenant_id=tenant.id)
    ctx, result = compute(claim)

    # The gross it read gets recomputed to a new value before it saves.
    writes.apply(tenant.id, [Assert("employee:1", "annual_salary_cents", Span(D(2024, 3, 1)), 1)])
    worker.drain("w", tenant_id=tenant.id)  # recomputes gross only, withholding is leased
    assert save(claim, ctx, result, "1") is SaveOutcome.REQUEUED
