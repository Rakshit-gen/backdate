"""Half-open date spans and the small amount of algebra the write path needs.

A span is [start, end). ``end=None`` means the span runs forever. Every
valid-time range in backdate goes through this type before it touches the
database, so the rules for splitting and trimming live in one place and can
be tested without Postgres.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from psycopg.types.range import Range

FOREVER: date | None = None


class SpanError(ValueError):
    pass


@dataclass(frozen=True, slots=True, order=True)
class Span:
    start: date
    end: date | None = None

    def __post_init__(self) -> None:
        if self.end is not None and self.end <= self.start:
            raise SpanError(f"empty or inverted span: [{self.start}, {self.end})")

    @classmethod
    def day(cls, d: date) -> Span:
        return cls(d, d + timedelta(days=1))

    @classmethod
    def everything(cls) -> Span:
        return cls(date.min, None)

    @property
    def is_open(self) -> bool:
        return self.end is None

    def contains(self, d: date) -> bool:
        return self.start <= d and (self.end is None or d < self.end)

    def overlaps(self, other: Span) -> bool:
        return _lt(self.start, other.end) and _lt(other.start, self.end)

    def touches(self, other: Span) -> bool:
        """True when the spans share a boundary and do not overlap."""
        return self.end == other.start or other.end == self.start

    def intersect(self, other: Span) -> Span | None:
        if not self.overlaps(other):
            return None
        start = max(self.start, other.start)
        end = _min_end(self.end, other.end)
        return Span(start, end)

    def minus(self, other: Span) -> list[Span]:
        """Parts of self that fall outside other, in order. Zero, one or two spans."""
        if not self.overlaps(other):
            return [self]
        pieces: list[Span] = []
        if self.start < other.start:
            pieces.append(Span(self.start, other.start))
        if other.end is not None and (self.end is None or other.end < self.end):
            pieces.append(Span(other.end, self.end))
        return pieces

    def days(self) -> int | None:
        if self.end is None:
            return None
        return (self.end - self.start).days

    def iter_days(self) -> Iterator[date]:
        if self.end is None:
            raise SpanError("cannot iterate the days of an open span")
        d = self.start
        while d < self.end:
            yield d
            d += timedelta(days=1)

    def to_range(self) -> Range[date]:
        return Range(self.start, self.end, "[)")

    @classmethod
    def from_range(cls, r: Range[date]) -> Span:
        if r.isempty:
            raise SpanError("empty range")
        lower = r.lower if r.lower is not None else date.min
        if not r.lower_inc and r.lower is not None:
            lower = lower + timedelta(days=1)
        upper = r.upper
        if upper is not None and r.upper_inc:
            upper = upper + timedelta(days=1)
        return cls(lower, upper)

    def __str__(self) -> str:
        end = "∞" if self.end is None else self.end.isoformat()
        return f"[{self.start.isoformat()}, {end})"


def _lt(a: date, b: date | None) -> bool:
    return b is None or a < b


def _min_end(a: date | None, b: date | None) -> date | None:
    if a is None:
        return b
    if b is None:
        return a
    return min(a, b)


def coalesce(pieces: Iterable[tuple[Span, Any]]) -> list[tuple[Span, Any]]:
    """Merge neighbouring pieces that carry equal values.

    Input must not overlap. Output is sorted by start, and no two touching
    pieces carry the same value, which makes it the canonical form of a
    timeline: two timelines that mean the same thing coalesce to equal lists.
    """
    ordered = sorted(pieces, key=lambda p: p[0].start)
    out: list[tuple[Span, Any]] = []
    for span, value in ordered:
        if out:
            prev_span, prev_value = out[-1]
            if prev_span.overlaps(span):
                raise SpanError(f"overlapping pieces {prev_span} and {span}")
            if prev_span.end == span.start and prev_value == value:
                out[-1] = (Span(prev_span.start, span.end), value)
                continue
        out.append((span, value))
    return out


def parse_span(start: str, end: str | None) -> Span:
    try:
        s = date.fromisoformat(start)
        e = date.fromisoformat(end) if end else None
    except ValueError as exc:
        raise SpanError(str(exc)) from exc
    return Span(s, e)
