"""Per-tenant knowledge clock.

The write protocol is:

1. ``lock_for_write`` takes the tenant's clock row with FOR UPDATE.
2. The writer computes its changes. If nothing changes, it stops here and
   no version is spent.
3. ``advance`` bumps the version while still holding the lock.
4. The transaction commits, releasing the lock.

Only one writer per tenant holds the lock at a time, so version N+1 can
never commit before version N. Readers rely on that.

Saves of derived results take the same row FOR SHARE. That blocks until any
in-flight writer commits, which is what closes the race between a write
invalidating a result and a worker saving that result. See
``backdate.derive.save`` for the full argument.

The cost is that writes within one tenant are serialized. Writes in
different tenants do not touch the same row.
"""

from __future__ import annotations

from django.db import connection

from backdate.models import TenantClock


class ClockNotLocked(RuntimeError):
    pass


def ensure_clock(tenant_id: int) -> None:
    TenantClock.objects.get_or_create(tenant_id=tenant_id)


def lock_for_write(tenant_id: int) -> int:
    """Lock the clock and return the current committed version."""
    _require_transaction()
    with connection.cursor() as cur:
        cur.execute(
            "SELECT version FROM backdate_tenantclock WHERE tenant_id = %s FOR UPDATE",
            [tenant_id],
        )
        row = cur.fetchone()
    if row is None:
        ensure_clock(tenant_id)
        return lock_for_write(tenant_id)
    return int(row[0])


def advance(tenant_id: int, locked_version: int) -> int:
    """Bump the version. Caller must hold the lock from ``lock_for_write``."""
    _require_transaction()
    with connection.cursor() as cur:
        cur.execute(
            "UPDATE backdate_tenantclock SET version = version + 1, updated_at = now() "
            "WHERE tenant_id = %s AND version = %s RETURNING version",
            [tenant_id, locked_version],
        )
        row = cur.fetchone()
    if row is None:
        raise ClockNotLocked(f"clock for tenant {tenant_id} moved under a held lock")
    return int(row[0])


def share_lock(tenant_id: int) -> int:
    """Wait for any in-flight writer, then return the committed version."""
    _require_transaction()
    with connection.cursor() as cur:
        cur.execute(
            "SELECT version FROM backdate_tenantclock WHERE tenant_id = %s FOR SHARE",
            [tenant_id],
        )
        row = cur.fetchone()
    return int(row[0]) if row else 0


def _require_transaction() -> None:
    if not connection.in_atomic_block:
        raise ClockNotLocked("clock locks only make sense inside transaction.atomic()")
