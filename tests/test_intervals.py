from datetime import date, timedelta

import pytest
from hypothesis import given
from psycopg.types.range import Range

from backdate.intervals import Span, SpanError, coalesce, parse_span
from tests.strategies import EPOCH, WINDOW_DAYS, spans

D = date


def days_of(span: Span, horizon: int = WINDOW_DAYS * 3) -> set[date]:
    end = span.end or EPOCH + timedelta(days=horizon)
    return {span.start + timedelta(days=i) for i in range((end - span.start).days)}


def test_rejects_empty_and_inverted():
    with pytest.raises(SpanError):
        Span(D(2024, 1, 2), D(2024, 1, 2))
    with pytest.raises(SpanError):
        Span(D(2024, 1, 2), D(2024, 1, 1))


def test_half_open_bounds():
    s = Span(D(2024, 1, 1), D(2024, 2, 1))
    assert s.contains(D(2024, 1, 31))
    assert not s.contains(D(2024, 2, 1))
    assert s.days() == 31


def test_open_span_contains_far_future():
    assert Span(D(2024, 1, 1)).contains(D(9999, 1, 1))


def test_touching_spans_do_not_overlap():
    a = Span(D(2024, 1, 1), D(2024, 2, 1))
    b = Span(D(2024, 2, 1), D(2024, 3, 1))
    assert not a.overlaps(b)
    assert a.touches(b)


def test_minus_splits_in_two():
    year = Span(D(2024, 1, 1), D(2025, 1, 1))
    march = Span(D(2024, 3, 1), D(2024, 4, 1))
    assert year.minus(march) == [
        Span(D(2024, 1, 1), D(2024, 3, 1)),
        Span(D(2024, 4, 1), D(2025, 1, 1)),
    ]


def test_minus_open_from_open():
    assert Span(D(2024, 1, 1)).minus(Span(D(2024, 6, 1))) == [Span(D(2024, 1, 1), D(2024, 6, 1))]


@given(spans(), spans())
def test_intersect_matches_day_sets(a, b):
    got = a.intersect(b)
    expected = days_of(a) & days_of(b)
    assert (days_of(got) if got else set()) == expected


@given(spans(), spans())
def test_minus_matches_day_sets(a, b):
    pieces = a.minus(b)
    covered = set().union(*(days_of(p) for p in pieces)) if pieces else set()
    assert covered == days_of(a) - days_of(b)
    for x, y in zip(pieces, pieces[1:], strict=False):
        assert x.end is not None and x.end < y.start


@given(spans(), spans())
def test_overlap_is_symmetric_and_agrees_with_intersect(a, b):
    assert a.overlaps(b) == b.overlaps(a) == (a.intersect(b) is not None)


@given(spans())
def test_range_round_trip(s):
    assert Span.from_range(s.to_range()) == s


def test_from_range_normalises_closed_bounds():
    r = Range(D(2024, 1, 1), D(2024, 1, 31), "[]")
    assert Span.from_range(r) == Span(D(2024, 1, 1), D(2024, 2, 1))


def test_coalesce_merges_equal_neighbours_only():
    a = Span(D(2024, 1, 1), D(2024, 2, 1))
    b = Span(D(2024, 2, 1), D(2024, 3, 1))
    c = Span(D(2024, 3, 1), D(2024, 4, 1))
    assert coalesce([(b, 1), (a, 1), (c, 2)]) == [(Span(a.start, b.end), 1), (c, 2)]


def test_coalesce_keeps_gaps():
    a = Span(D(2024, 1, 1), D(2024, 2, 1))
    c = Span(D(2024, 3, 1), D(2024, 4, 1))
    assert coalesce([(a, 1), (c, 1)]) == [(a, 1), (c, 1)]


def test_coalesce_rejects_overlap():
    with pytest.raises(SpanError):
        coalesce([(Span(D(2024, 1, 1), D(2024, 3, 1)), 1), (Span(D(2024, 2, 1)), 1)])


def test_parse_span():
    assert parse_span("2024-01-01", None) == Span(D(2024, 1, 1))
    with pytest.raises(SpanError):
        parse_span("2024-13-01", None)
