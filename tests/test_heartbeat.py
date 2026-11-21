"""A derivation that runs longer than its lease keeps the lease, instead of being fenced forever."""

from __future__ import annotations

import threading
import time
from datetime import date

import pytest
from django.db import connections

import tests.slow_derivations  # noqa: F401 - registers test.slow in this process
from backdate import writes
from backdate.derive import worker
from backdate.intervals import Span
from backdate.models import Computation
from backdate.writes import Assert

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.slow]
JAN = Span(date(2024, 1, 1))


@pytest.fixture
def one_second_lease(settings):
    settings.BACKDATE = {**settings.BACKDATE, "LEASE_SECONDS": 1}


def slow_job(tenant, sleep_ms):
    writes.apply(
        tenant.id, [Assert("job", "sleep_ms", JAN, sleep_ms), Assert("job", "value", JAN, 7)]
    )
    worker.request(tenant.id, "test.slow", ["job"])


def test_long_derivation_keeps_its_lease_and_saves(tenant, one_second_lease):
    slow_job(tenant, 2_500)
    (claim,) = worker.claim("slow", tenant_id=tenant.id)
    result: list[worker.RunResult] = []

    def run() -> None:
        try:
            result.append(worker.run_one(claim))
        finally:
            connections.close_all()

    t = threading.Thread(target=run)
    t.start()

    stolen = []
    while t.is_alive():
        stolen += worker.claim("thief", tenant_id=tenant.id)
        time.sleep(0.1)
    t.join()

    assert stolen == [], "the lease ran out while the derivation was still computing"
    assert result[0].outcome == "saved"
    c = Computation.objects.get(key="job")
    assert (c.status, c.result, c.lease_token) == ("fresh", {"value": 7}, claim.token)


def test_heartbeat_does_not_revive_a_lease_someone_else_took(tenant, one_second_lease):
    slow_job(tenant, 0)
    (old,) = worker.claim("old", tenant_id=tenant.id)
    Computation.objects.filter(id=old.computation_id).update(lease_token=old.token + 1)
    assert worker.extend_lease(old) is False
    c = Computation.objects.get(id=old.computation_id)
    assert c.lease_token == old.token + 1
