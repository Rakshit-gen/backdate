from datetime import date

import pytest

from backdate.derive.context import Context
from backdate.intervals import Span
from backdate.reads import Piece
from examples.payroll.derivations import BadKey, gross, parse_key


@pytest.mark.parametrize(
    ("key", "span"),
    [
        ("7:2024-02", Span(date(2024, 2, 1), date(2024, 3, 1))),
        ("7:2024-12", Span(date(2024, 12, 1), date(2025, 1, 1))),
        ("abc:2023-02", Span(date(2023, 2, 1), date(2023, 3, 1))),
    ],
)
def test_parse_key(key, span):
    entity, got = parse_key(key)
    assert entity == f"employee:{key.split(':')[0]}"
    assert got == span


@pytest.mark.parametrize("key", ["", "7", "7:2024", "7:2024-13", ":2024-01", "7:24-1-1", "a:b:c"])
def test_parse_key_rejects(key):
    with pytest.raises(BadKey):
        parse_key(key)


class FakeContext(Context):
    """Serves timelines from a dict so the arithmetic can be tested alone."""

    def __init__(self, data):
        super().__init__(tenant_id=0, version=0)
        self.data = data

    def timeline(self, entity, attribute, within):
        out = []
        for span, value in self.data.get(attribute, []):
            clipped = span.intersect(within)
            if clipped:
                out.append(Piece(clipped, value))
        return out


def test_leap_february_has_29_paid_days():
    ctx = FakeContext(
        {
            "annual_salary_cents": [(Span(date(2024, 1, 1)), 36_500_00)],
            "fte_bp": [(Span(date(2024, 1, 1)), 10_000)],
        }
    )
    assert gross(ctx, "1:2024-02") == {"gross_cents": 29 * 100_00, "days_paid": 29}


def test_no_fte_means_no_pay():
    ctx = FakeContext({"annual_salary_cents": [(Span(date(2024, 1, 1)), 36_500_00)]})
    assert gross(ctx, "1:2024-02") == {"gross_cents": 0, "days_paid": 0}


def test_rounding_happens_once_per_month():
    # Rounding each day would lose the fractions; rounding the month total keeps them.
    ctx = FakeContext(
        {
            "annual_salary_cents": [(Span(date(2024, 1, 1)), 1)],
            "fte_bp": [(Span(date(2024, 1, 1)), 10_000)],
        }
    )
    assert gross(ctx, "1:2024-01")["gross_cents"] == 0
    ctx.data["annual_salary_cents"] = [(Span(date(2024, 1, 1)), 365 * 100 + 50)]
    # 36550 / 365 * 31 = 3104.2465... -> 3104
    assert gross(ctx, "1:2024-01")["gross_cents"] == 3104
