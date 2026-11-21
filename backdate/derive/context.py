"""What a derivation sees while it runs.

All fact reads are pinned to one version, picked before the derivation
starts, and every read is written down. When the result is saved, those
reads become ``ReadRange`` rows, and a later write that overlaps any of them
marks the result stale.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from django.db import connection

from backdate import reads
from backdate.intervals import Span
from backdate.models import Computation


class NotReady(Exception):
    """A derivation needs another result that is not computed yet.

    The worker puts the reader back in the queue and makes sure the source
    is queued too. This is retry, not failure, so it does not count towards
    ``MAX_ATTEMPTS``.
    """

    def __init__(self, derivation: str, key: str) -> None:
        super().__init__(f"{derivation}({key}) is not fresh yet")
        self.derivation = derivation
        self.key = key


class ReadOutsideContext(RuntimeError):
    """A derivation queried the database without going through ``ctx``.

    Nothing records what such a query read, so no later write could mark the
    result stale. With ``STRICT_READS`` on, the worker fails the computation
    for good instead of saving a result that can silently go wrong.
    """


@dataclass(frozen=True, slots=True)
class DerivedObservation:
    computation_id: int
    seq: int


@dataclass
class Context:
    tenant_id: int
    version: int
    _reads: dict[tuple[str, str], list[Span]] = field(default_factory=lambda: defaultdict(list))
    _derived: dict[tuple[str, str], DerivedObservation] = field(default_factory=dict)
    _inside: int = 0
    violation: str | None = None

    @contextmanager
    def _recorded(self) -> Iterator[None]:
        self._inside += 1
        try:
            yield
        finally:
            self._inside -= 1

    def timeline(self, entity: str, attribute: str, within: Span) -> list[reads.Piece]:
        self._reads[(entity, attribute)].append(within)
        with self._recorded():
            return reads.timeline(
                self.tenant_id, entity, attribute, within=within, version=self.version
            )

    def value_at(self, entity: str, attribute: str, day: date) -> Any | None:
        self._reads[(entity, attribute)].append(Span.day(day))
        with self._recorded():
            return reads.value_at(self.tenant_id, entity, attribute, day, version=self.version)

    def derived(self, derivation: str, key: str) -> Any:
        """Result of another derivation. Raises NotReady if it is not fresh."""
        with self._recorded():
            comp = (
                Computation.objects.filter(tenant_id=self.tenant_id, derivation=derivation, key=key)
                .only("id", "status", "result", "result_seq")
                .first()
            )
        if comp is None or comp.status != Computation.Status.FRESH:
            raise NotReady(derivation, key)
        self._derived[(derivation, key)] = DerivedObservation(comp.id, comp.result_seq)
        return comp.result

    def read_set(self) -> list[tuple[str, str, Span]]:
        """Reads merged per attribute, so a month of daily lookups is one row."""
        out: list[tuple[str, str, Span]] = []
        for (entity, attribute), spans in sorted(self._reads.items()):
            for span in merge_spans(spans):
                out.append((entity, attribute, span))
        return out

    def derived_reads(self) -> list[DerivedObservation]:
        return list(self._derived.values())


@contextmanager
def strict_reads(ctx: Context) -> Iterator[None]:
    """Reject any query on this thread's connection that does not come from ``ctx``.

    The first offending query is kept on ``ctx.violation``, so a derivation
    that catches the error still fails.
    """

    def guard(execute: Callable[..., Any], sql: str, params: Any, many: bool, context: Any) -> Any:
        if not ctx._inside:
            ctx.violation = (
                ctx.violation or f"derivation queried the database outside ctx: {sql[:200]}"
            )
            raise ReadOutsideContext(ctx.violation)
        return execute(sql, params, many, context)

    with connection.execute_wrapper(guard):
        yield


def merge_spans(spans: list[Span]) -> list[Span]:
    """Union of spans, as the fewest sorted spans that cover it."""
    merged: list[Span] = []
    for span in sorted(spans):
        if merged:
            last = merged[-1]
            if last.overlaps(span) or last.end == span.start:
                end = None if last.end is None or span.end is None else max(last.end, span.end)
                merged[-1] = Span(last.start, end)
                continue
        merged.append(span)
    return merged
