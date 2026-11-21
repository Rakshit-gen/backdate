"""A dry run answers "what would this backdate change?" and leaves no trace."""

from datetime import date

import pytest

from backdate import reads, writes
from backdate.derive import worker
from backdate.intervals import Span
from backdate.models import ChangeRange, Changeset, Computation, Fact
from backdate.writes import Assert
from tests.test_derive_flow import hire

pytestmark = pytest.mark.django_db
D = date


def computed(tenant):
    hire(tenant)
    worker.request(tenant.id, "payroll.gross", [f"1:2024-{m:02d}" for m in range(1, 7)])
    worker.drain("t", tenant_id=tenant.id)


def raise_from_april():
    return [Assert("employee:1", "annual_salary_cents", Span(D(2024, 4, 1)), 73_000_00)]


def snapshot(tenant):
    return (
        reads.committed_version(tenant.id),
        Fact.objects.filter(tenant=tenant).count(),
        Changeset.objects.filter(tenant=tenant).count(),
        ChangeRange.objects.filter(tenant=tenant).count(),
        sorted(Computation.objects.filter(tenant=tenant).values_list("key", "status")),
    )


def test_dry_run_lists_what_would_go_stale_and_changes_nothing(tenant):
    computed(tenant)
    before = snapshot(tenant)

    result = writes.apply(tenant.id, raise_from_april(), dry_run=True)

    assert result.dry_run
    assert result.version == before[0] + 1
    assert result.invalidated == 3
    assert sorted(k for _, k in result.affected) == ["1:2024-04", "1:2024-05", "1:2024-06"]
    assert snapshot(tenant) == before


def test_dry_run_then_real_write_agree(tenant):
    computed(tenant)
    dry = writes.apply(tenant.id, raise_from_april(), dry_run=True)
    real = writes.apply(tenant.id, raise_from_april())
    assert (real.version, real.invalidated, real.changes) == (
        dry.version,
        dry.invalidated,
        dry.changes,
    )


def test_dry_run_of_a_noop_says_so(tenant):
    computed(tenant)
    result = writes.apply(
        tenant.id,
        [Assert("employee:1", "annual_salary_cents", Span(D(2024, 1, 1)), 36_500_00)],
        dry_run=True,
    )
    assert result.noop
    assert result.affected == []


def test_dry_run_over_the_api(api, tenant):
    body = {
        "dry_run": True,
        "ops": [
            {
                "op": "assert",
                "entity": "employee:1",
                "attribute": "fte_bp",
                "from": "2024-01-01",
                "value": 5000,
            }
        ],
    }
    r = api.post("/v1/writes", body, HTTP_IDEMPOTENCY_KEY="dry-1")
    assert r.status_code == 200
    data = r.json()
    assert data["dry_run"] is True
    assert data["version"] == 1
    assert data["affected"] == []
    assert reads.committed_version(tenant.id) == 0
    # A dry run never claims an idempotency key, so the real write can still use it.
    body["dry_run"] = False
    assert api.post("/v1/writes", body, HTTP_IDEMPOTENCY_KEY="dry-1").json()["version"] == 1
