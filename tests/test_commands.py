from datetime import date
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from backdate.api import keys
from backdate.derive import worker
from backdate.intervals import Span
from backdate.models import Computation, Tenant
from backdate.writes import Assert, apply

pytestmark = pytest.mark.django_db


def run(*args):
    out = StringIO()
    call_command(*args, stdout=out)
    return out.getvalue().strip()


def test_create_tenant_prints_a_working_key():
    token = run("create_tenant", "acme", "--scopes", "read")
    principal = keys.authenticate(token)
    assert principal.scopes == {"read"}
    assert Tenant.objects.get(slug="acme").tenantclock.version == 0


def test_create_tenant_twice_adds_a_second_key():
    first = run("create_tenant", "acme")
    second = run("create_tenant", "acme")
    assert first != second
    assert Tenant.objects.filter(slug="acme").count() == 1


def test_create_tenant_rejects_bad_scope():
    with pytest.raises(CommandError):
        run("create_tenant", "acme", "--scopes", "root")


def test_seed_then_drain_computes_everything():
    run("create_tenant", "demo")
    assert "queued 48" in run("seed_payroll", "demo", "--employees", "2")
    assert "computed 48" in run("backdate_worker", "--once")
    assert not Computation.objects.exclude(status="fresh").exists()


def test_seed_needs_a_tenant():
    with pytest.raises(CommandError):
        run("seed_payroll", "missing")


def test_rebase_marks_old_code_stale(tenant):
    apply(tenant.id, [Assert("employee:1", "annual_salary_cents", Span(date(2024, 1, 1)), 1)])
    worker.request(tenant.id, "payroll.gross", ["1:2024-01"])
    worker.drain("t", tenant_id=tenant.id)
    assert "0 results" in run("backdate_rebase", "payroll.gross")
    Computation.objects.update(code_version="0")
    assert "1 results" in run("backdate_rebase", "payroll.gross")
    assert Computation.objects.get().status == "stale"
