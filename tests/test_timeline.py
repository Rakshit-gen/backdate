"""Timeline operations checked against a day-by-day dictionary model."""

from datetime import date, timedelta

from hypothesis import given
from hypothesis import strategies as st

from backdate.intervals import Span, coalesce
from backdate.timeline import assert_value, changed_spans, retract
from tests.strategies import EPOCH, WINDOW_DAYS, spans, values

HORIZON = WINDOW_DAYS * 3


def to_days(timeline) -> dict[date, int]:
    out = {}
    for span, value in timeline:
        end = span.end or EPOCH + timedelta(days=HORIZON)
        d = span.start
        while d < end:
            out[d] = value
            d += timedelta(days=1)
    return out


def span_days(span: Span) -> list[date]:
    end = span.end or EPOCH + timedelta(days=HORIZON)
    return [span.start + timedelta(days=i) for i in range((end - span.start).days)]


ops = st.lists(
    st.one_of(
        st.tuples(st.just("set"), spans(), values),
        st.tuples(st.just("del"), spans(), st.none()),
    ),
    max_size=8,
)


def run(op_list):
    timeline = []
    model: dict[date, int] = {}
    for kind, span, value in op_list:
        if kind == "set":
            timeline = assert_value(timeline, span, value)
            for d in span_days(span):
                model[d] = value
        else:
            timeline = retract(timeline, span)
            for d in span_days(span):
                model.pop(d, None)
    return timeline, model


@given(ops)
def test_operations_match_day_model(op_list):
    timeline, model = run(op_list)
    assert to_days(timeline) == model


@given(ops)
def test_result_is_canonical(op_list):
    timeline, _ = run(op_list)
    assert coalesce(timeline) == timeline


@given(ops, ops)
def test_changed_spans_are_exactly_the_differing_days(first, second):
    before, before_model = run(first)
    after, _ = run(first + second)
    after_model = to_days(after)
    changed = set()
    for span in changed_spans(before, after):
        changed.update(span_days(span))
    all_days = set(before_model) | set(after_model)
    differing = {d for d in all_days if before_model.get(d) != after_model.get(d)}
    assert changed == differing


def test_rewriting_same_value_changes_nothing():
    jan = Span(date(2024, 1, 1), date(2024, 2, 1))
    timeline = assert_value([], Span(date(2024, 1, 1)), 5)
    assert changed_spans(timeline, assert_value(timeline, jan, 5)) == []


def test_raise_in_the_middle_splits_the_old_value():
    timeline = assert_value([], Span(date(2024, 1, 1)), 100)
    timeline = assert_value(timeline, Span(date(2024, 3, 1), date(2024, 4, 1)), 120)
    assert timeline == [
        (Span(date(2024, 1, 1), date(2024, 3, 1)), 100),
        (Span(date(2024, 3, 1), date(2024, 4, 1)), 120),
        (Span(date(2024, 4, 1)), 100),
    ]
