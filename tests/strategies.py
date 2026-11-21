"""Hypothesis strategies shared by the property tests."""

from __future__ import annotations

from datetime import date, timedelta

from hypothesis import strategies as st

from backdate.intervals import Span

EPOCH = date(2024, 1, 1)
# A short window keeps generated spans colliding with each other often,
# which is where the interesting cases are.
WINDOW_DAYS = 60


@st.composite
def spans(draw, *, allow_open: bool = True) -> Span:
    start = draw(st.integers(0, WINDOW_DAYS - 1))
    if allow_open and draw(st.integers(0, 5)) == 0:
        return Span(EPOCH + timedelta(days=start), None)
    length = draw(st.integers(1, WINDOW_DAYS))
    return Span(EPOCH + timedelta(days=start), EPOCH + timedelta(days=start + length))


values = st.integers(0, 3)
