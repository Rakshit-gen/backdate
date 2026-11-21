"""A derivation whose run time is a fact, so tests can hold a worker mid-compute."""

from __future__ import annotations

import time
from datetime import date

from backdate.derive.context import Context
from backdate.derive.registry import derivation


@derivation("test.slow")
def slow(ctx: Context, key: str) -> dict[str, int]:
    """Sleeps for the 'sleep_ms' fact of the key, then echoes 'value'."""
    day = date(2024, 1, 1)
    sleep_ms = ctx.value_at(key, "sleep_ms", day) or 0
    time.sleep(sleep_ms / 1000)
    return {"value": ctx.value_at(key, "value", day) or 0}
