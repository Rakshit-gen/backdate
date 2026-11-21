"""Issuing and checking API keys.

A key looks like ``bk_<prefix>_<secret>``. The prefix is stored in the
clear and indexed, so lookup is one query. The secret is stored as a
SHA-256 digest. It has 256 bits of entropy, so a fast hash is fine here;
a slow password hash would only cost latency on every request.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from collections.abc import Iterable
from dataclasses import dataclass

from backdate.models import ApiKey, Tenant

SCOPES = frozenset({"read", "write", "compute"})
_PREFIX_BYTES = 6
_SECRET_BYTES = 32


class InvalidKey(Exception):
    pass


@dataclass(frozen=True, slots=True)
class Principal:
    tenant_id: int
    key_id: int
    scopes: frozenset[str]


def issue(tenant: Tenant, scopes: Iterable[str], label: str = "") -> tuple[ApiKey, str]:
    """Create a key. The plaintext is returned once and never stored."""
    wanted = frozenset(scopes)
    unknown = wanted - SCOPES
    if unknown:
        raise ValueError(f"unknown scopes: {sorted(unknown)}")
    prefix = secrets.token_hex(_PREFIX_BYTES)
    secret = secrets.token_urlsafe(_SECRET_BYTES)
    key = ApiKey.objects.create(
        tenant=tenant,
        prefix=prefix,
        secret_hash=_digest(secret),
        scopes=sorted(wanted),
        label=label,
    )
    return key, f"bk_{prefix}_{secret}"


def authenticate(token: str) -> Principal:
    try:
        marker, prefix, secret = token.split("_", 2)
    except ValueError:
        raise InvalidKey("malformed key") from None
    if marker != "bk" or not prefix or not secret:
        raise InvalidKey("malformed key")
    key = (
        ApiKey.objects.filter(prefix=prefix, revoked_at__isnull=True)
        .only("id", "tenant_id", "secret_hash", "scopes")
        .first()
    )
    # Compare against a dummy digest when the prefix is unknown so both
    # paths do the same work.
    expected = key.secret_hash if key else _digest("x" * 43)
    if not hmac.compare_digest(expected, _digest(secret)) or key is None:
        raise InvalidKey("unknown or revoked key")
    return Principal(key.tenant_id, key.id, frozenset(key.scopes))


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()
