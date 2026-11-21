from __future__ import annotations

import itertools

import pytest

from backdate.api import keys
from backdate.models import Tenant, TenantClock

_slugs = itertools.count()


@pytest.fixture
def tenant(db):
    t = Tenant.objects.create(slug=f"t{next(_slugs)}", name="Test tenant")
    TenantClock.objects.create(tenant=t)
    return t


@pytest.fixture
def other_tenant(db):
    t = Tenant.objects.create(slug=f"o{next(_slugs)}", name="Other tenant")
    TenantClock.objects.create(tenant=t)
    return t


class Api:
    """Thin JSON client bound to one API key."""

    def __init__(self, client, token: str) -> None:
        self.client = client
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def get(self, path, **params):
        return self.client.get(path, params, **self.headers)

    def post(self, path, body, **headers):
        return self.client.post(
            path, data=body, content_type="application/json", **self.headers, **headers
        )


@pytest.fixture
def api(client, tenant):
    _, token = keys.issue(tenant, ["read", "write", "compute"])
    return Api(client, token)


@pytest.fixture
def other_api(client, other_tenant):
    _, token = keys.issue(other_tenant, ["read", "write", "compute"])
    return Api(client, token)
