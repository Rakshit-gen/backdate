"""Pin a database session to one tenant for row-level security."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from django.db import connection


@contextmanager
def scoped(tenant_id: int) -> Iterator[None]:
    with connection.cursor() as cur:
        cur.execute("SELECT set_config('backdate.tenant_id', %s, false)", [str(tenant_id)])
    try:
        yield
    finally:
        # A pooled connection must not carry one tenant's setting into the
        # next request. If the connection is already broken there is
        # nothing to reset.
        if connection.connection is not None and connection.is_usable():
            with connection.cursor() as cur:
                cur.execute("SELECT set_config('backdate.tenant_id', '', false)")
