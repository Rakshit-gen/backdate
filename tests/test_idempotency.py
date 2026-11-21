from datetime import date

import pytest

from backdate import writes
from backdate.intervals import Span
from backdate.models import Changeset
from backdate.writes import Assert

pytestmark = pytest.mark.django_db

OPS = [Assert("e", "a", Span(date(2024, 1, 1)), 1)]


def test_same_key_replays_the_first_response(tenant):
    first = writes.apply(tenant.id, OPS, idempotency_key="k1", request_hash="h")
    second = writes.apply(tenant.id, OPS, idempotency_key="k1", request_hash="h")
    assert second.replayed
    assert second.as_json() == first.as_json()
    assert Changeset.objects.filter(tenant=tenant).count() == 1


def test_replay_survives_later_writes(tenant):
    first = writes.apply(tenant.id, OPS, idempotency_key="k1", request_hash="h")
    writes.apply(tenant.id, [Assert("e", "a", Span(date(2024, 1, 1)), 2)])
    again = writes.apply(tenant.id, OPS, idempotency_key="k1", request_hash="h")
    assert again.version == first.version == 1


def test_same_key_different_body_is_rejected(tenant):
    writes.apply(tenant.id, OPS, idempotency_key="k1", request_hash="h")
    with pytest.raises(writes.IdempotencyConflict):
        writes.apply(tenant.id, OPS, idempotency_key="k1", request_hash="other")


def test_keys_are_scoped_per_tenant(tenant, other_tenant):
    writes.apply(tenant.id, OPS, idempotency_key="k1", request_hash="h")
    result = writes.apply(other_tenant.id, OPS, idempotency_key="k1", request_hash="h")
    assert not result.replayed


def test_noop_writes_are_recorded_too(tenant):
    writes.apply(tenant.id, OPS)
    first = writes.apply(tenant.id, OPS, idempotency_key="k2", request_hash="h")
    assert first.noop
    assert writes.apply(tenant.id, OPS, idempotency_key="k2", request_hash="h").replayed
