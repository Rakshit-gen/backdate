"""Model-based test: the database against a dictionary of snapshots.

The model keeps, for every version, the full day-by-day state of every
attribute. Any read at any past version must agree with the snapshot taken
when that version was written, which is the bitemporal promise.
"""

from __future__ import annotations

import itertools
from datetime import date, timedelta

import pytest
from hypothesis import settings
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule, run_state_machine_as_test

from backdate import reads, writes
from backdate.intervals import Span, coalesce
from backdate.models import Fact, Tenant, TenantClock
from backdate.writes import Assert, Retract
from tests.strategies import EPOCH, WINDOW_DAYS, spans, values

HORIZON = WINDOW_DAYS * 3
KEYS = [("e1", "a"), ("e1", "b"), ("e2", "a")]
_ids = itertools.count()

State = dict[tuple[str, str], dict[date, int]]


def span_days(span: Span) -> list[date]:
    end = span.end or EPOCH + timedelta(days=HORIZON)
    return [span.start + timedelta(days=i) for i in range((end - span.start).days)]


class BitemporalMachine(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.tenant = Tenant.objects.create(slug=f"m{next(_ids)}", name="model")
        TenantClock.objects.create(tenant=self.tenant)
        self.snapshots: list[State] = [{k: {} for k in KEYS}]

    @property
    def state(self) -> State:
        return self.snapshots[-1]

    def _commit(self, new: State, result: writes.WriteResult) -> None:
        if new == self.state:
            assert result.noop, "a write that changes nothing must not spend a version"
            assert result.version == len(self.snapshots) - 1
        else:
            assert not result.noop
            assert result.version == len(self.snapshots)
            self.snapshots.append(new)

    @rule(key=st.sampled_from(KEYS), span=spans(), value=values)
    def assert_value(self, key, span, value):
        new = {k: dict(v) for k, v in self.state.items()}
        for d in span_days(span):
            new[key][d] = value
        result = writes.apply(self.tenant.id, [Assert(*key, span, value)])
        self._commit(new, result)

    @rule(key=st.sampled_from(KEYS), span=spans())
    def retract(self, key, span):
        new = {k: dict(v) for k, v in self.state.items()}
        for d in span_days(span):
            new[key].pop(d, None)
        result = writes.apply(self.tenant.id, [Retract(*key, span)])
        self._commit(new, result)

    @rule(data=st.data())
    def read_at_some_version(self, data):
        version = data.draw(st.integers(0, len(self.snapshots) - 1))
        key = data.draw(st.sampled_from(KEYS))
        day = EPOCH + timedelta(days=data.draw(st.integers(0, HORIZON - 1)))
        got = reads.value_at(self.tenant.id, *key, day, version=version)
        assert got == self.snapshots[version][key].get(day)

    @rule(data=st.data())
    def timeline_at_some_version(self, data):
        version = data.draw(st.integers(0, len(self.snapshots) - 1))
        key = data.draw(st.sampled_from(KEYS))
        pieces = reads.timeline(self.tenant.id, *key, version=version)
        days: dict[date, int] = {}
        for p in pieces:
            for d in span_days(p.span):
                days[d] = p.value
        expected = self.snapshots[version][key]
        assert {d: v for d, v in days.items() if d < EPOCH + timedelta(HORIZON)} == expected

    @invariant()
    def current_rows_are_canonical(self):
        for entity, attribute in KEYS:
            rows = Fact.objects.filter(
                tenant=self.tenant, entity=entity, attribute=attribute, tx_to__isnull=True
            ).values_list("valid", "value")
            pieces = sorted((Span.from_range(v), x) for v, x in rows)
            assert coalesce(pieces) == pieces


@pytest.mark.django_db
def test_database_matches_snapshot_model():
    run_state_machine_as_test(
        BitemporalMachine,
        settings=settings(max_examples=60, stateful_step_count=25, deadline=None),
    )
