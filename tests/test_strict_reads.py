"""A derivation that reads the database outside ctx fails loudly instead of going stale silently."""

from datetime import date

import pytest

import tests.slow_derivations  # noqa: F401 - registers the test derivations
from backdate import writes
from backdate.derive import worker
from backdate.intervals import Span
from backdate.models import Computation
from backdate.writes import Assert

pytestmark = pytest.mark.django_db
JAN = Span(date(2024, 1, 1))


def run(tenant, derivation):
    writes.apply(tenant.id, [Assert("job", "value", JAN, 1)])
    worker.request(tenant.id, derivation, ["job"])
    (claim,) = worker.claim("w", tenant_id=tenant.id)
    outcome = worker.run_one(claim).outcome
    return outcome, Computation.objects.get(derivation=derivation, key="job")


def test_query_outside_ctx_fails_for_good(tenant):
    outcome, c = run(tenant, "test.sneaky")
    assert outcome == "failed"
    assert c.status == "failed"
    assert "outside ctx" in c.last_error
    assert "backdate_fact" in c.last_error


def test_swallowing_the_error_does_not_help(tenant):
    outcome, c = run(tenant, "test.swallow")
    assert outcome == "failed"
    assert "outside ctx" in c.last_error


def test_reads_through_ctx_are_fine(tenant):
    outcome, c = run(tenant, "test.slow")
    assert (outcome, c.result) == ("saved", {"value": 1})


def test_strict_reads_can_be_turned_off(tenant, settings):
    settings.BACKDATE = {**settings.BACKDATE, "STRICT_READS": False}
    outcome, c = run(tenant, "test.sneaky")
    assert (outcome, c.result) == ("saved", {"rows": 1})
