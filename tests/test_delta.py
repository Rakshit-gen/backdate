from hypothesis import given
from hypothesis import strategies as st

from backdate.derive.save import delta


def test_first_statement_delta_is_the_value():
    assert delta(None, {"gross_cents": 500, "days": 31}) == {"gross_cents": 500, "days": 31}


def test_unchanged_fields_are_left_out():
    assert delta({"a": 1, "b": 2}, {"a": 1, "b": 5}) == {"b": 3}


def test_removed_numeric_field_is_reversed():
    assert delta({"a": 4, "b": 1}, {"b": 1}) == {"a": -4}


def test_non_numeric_fields_have_no_delta():
    assert delta({"state": "KA", "n": 1}, {"state": "MH", "n": 1}) == {}


def test_bools_are_not_numbers():
    assert delta({"ok": False}, {"ok": True}) == {}


def test_scalars():
    assert delta(None, 7) == 7
    assert delta(7, 10) == 3


@given(st.lists(st.dictionaries(st.sampled_from("abc"), st.integers(-(10**9), 10**9)), min_size=1))
def test_deltas_sum_to_last_value(history):
    totals: dict[str, int] = {}
    previous = None
    for current in history:
        for k, v in delta(previous, current).items():
            totals[k] = totals.get(k, 0) + v
        previous = current
    last = history[-1]
    for k in set(totals) | set(last):
        assert totals.get(k, 0) == last.get(k, 0), k
