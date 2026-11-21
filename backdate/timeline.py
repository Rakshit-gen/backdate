"""Pure operations on one attribute's timeline.

A timeline is a list of ``(Span, value)`` pairs that do not overlap. These
functions are what UPDATE/DELETE ... FOR PORTION OF would do in SQL:2011.
Postgres does not ship that yet, so the write path computes the result here
and then writes the difference.

Nothing in this module touches the database.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from itertools import pairwise
from typing import Any

from backdate.intervals import Span, coalesce

Timeline = list[tuple[Span, Any]]

_MISSING = object()


def without(timeline: Sequence[tuple[Span, Any]], portion: Span) -> Timeline:
    """Remove ``portion``, keeping the leftovers on either side."""
    out: Timeline = []
    for span, value in timeline:
        out.extend((piece, value) for piece in span.minus(portion))
    return out


def assert_value(timeline: Sequence[tuple[Span, Any]], portion: Span, value: Any) -> Timeline:
    """Say that the attribute holds ``value`` for all of ``portion``."""
    return coalesce([*without(timeline, portion), (portion, value)])


def retract(timeline: Sequence[tuple[Span, Any]], portion: Span) -> Timeline:
    """Say that the attribute has no value anywhere in ``portion``."""
    return coalesce(without(timeline, portion))


def value_on(timeline: Sequence[tuple[Span, Any]], day: date) -> Any:
    for span, value in timeline:
        if span.contains(day):
            return value
    return _MISSING


def changed_spans(
    before: Sequence[tuple[Span, Any]], after: Sequence[tuple[Span, Any]]
) -> list[Span]:
    """Valid-time spans where the two timelines disagree, merged and sorted.

    A day with a value on one side and none on the other counts as changed.
    Re-splitting a run without changing its values does not.
    """
    cuts: set[date] = set()
    open_ended = False
    for span, _ in (*before, *after):
        cuts.add(span.start)
        if span.end is None:
            open_ended = True
        else:
            cuts.add(span.end)
    if not cuts:
        return []
    points = sorted(cuts)
    segments = [Span(a, b) for a, b in pairwise(points)]
    if open_ended:
        segments.append(Span(points[-1], None))

    changed: list[tuple[Span, Any]] = []
    for seg in segments:
        if _differs(value_on(before, seg.start), value_on(after, seg.start)):
            changed.append((seg, True))
    return [span for span, _ in coalesce(changed)]


def _differs(a: Any, b: Any) -> bool:
    if a is _MISSING or b is _MISSING:
        return a is not b
    return bool(a != b)
