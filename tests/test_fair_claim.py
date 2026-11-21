"""One tenant's big backdate must not starve every other tenant's workers."""

from datetime import date

import pytest

import tests.slow_derivations  # noqa: F401 - registers test.slow
from backdate import writes
from backdate.derive import worker
from backdate.intervals import Span
from backdate.writes import Assert

pytestmark = pytest.mark.django_db
JAN = Span(date(2024, 1, 1))


def queue(tenant, n, prefix):
    keys = [f"{prefix}{i}" for i in range(n)]
    writes.apply(tenant.id, [Assert(k, "value", JAN, 1) for k in keys])
    worker.request(tenant.id, "test.slow", keys)


def test_small_tenant_gets_work_claimed_next_to_a_big_backlog(tenant, other_tenant):
    queue(tenant, 40, "big")  # queued first, so these have the lowest ids
    queue(other_tenant, 2, "small")
    claims = worker.claim("w", limit=4)
    by_tenant = {t: sum(c.tenant_id == t for c in claims) for t in (tenant.id, other_tenant.id)}
    assert by_tenant == {tenant.id: 2, other_tenant.id: 2}


def test_a_lone_tenant_still_fills_the_batch(tenant):
    queue(tenant, 10, "k")
    assert len(worker.claim("w", limit=6)) == 6


def test_claims_within_a_tenant_stay_oldest_first(tenant):
    queue(tenant, 5, "k")
    keys = sorted(c.key for c in worker.claim("w", limit=3))
    assert keys == ["k0", "k1", "k2"]
