from __future__ import annotations

import itertools

import pytest

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
