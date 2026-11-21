"""A derivation whose run time is a fact, so tests can hold a worker mid-compute."""

from __future__ import annotations

import contextlib
import time
from datetime import date

from backdate.derive.context import Context
from backdate.derive.registry import derivation
from backdate.models import Fact


@derivation("test.slow")
def slow(ctx: Context, key: str) -> dict[str, int]:
    """Sleeps for the 'sleep_ms' fact of the key, then echoes 'value'."""
    day = date(2024, 1, 1)
    sleep_ms = ctx.value_at(key, "sleep_ms", day) or 0
    time.sleep(sleep_ms / 1000)
    return {"value": ctx.value_at(key, "value", day) or 0}


@derivation("test.sneaky")
def sneaky(ctx: Context, key: str) -> dict[str, int]:
    """Reads a fact behind ctx's back, so nothing records the dependency."""
    return {"rows": Fact.objects.filter(tenant_id=ctx.tenant_id, entity=key).count()}


@derivation("test.swallow")
def swallow(ctx: Context, key: str) -> dict[str, int]:
    """Same, but hides the error, which must not let it through."""
    with contextlib.suppress(Exception):
        Fact.objects.filter(tenant_id=ctx.tenant_id).count()
    return {"rows": 0}
