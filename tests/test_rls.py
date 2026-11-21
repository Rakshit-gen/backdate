"""Row-level security, checked as a non-owner role (owners bypass RLS)."""

from __future__ import annotations

from datetime import date

import pytest
from django.db import connection, transaction

from backdate import reads, tenancy, writes
from backdate.intervals import Span
from backdate.writes import Assert

pytestmark = pytest.mark.django_db
ROLE = "backdate_rls_probe"


@pytest.fixture
def as_app_role(db):
    with connection.cursor() as cur:
        cur.execute(
            f"""
            DO $$ BEGIN
              IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{ROLE}') THEN
                CREATE ROLE {ROLE} NOLOGIN NOSUPERUSER NOBYPASSRLS;
              END IF;
            END $$;
            GRANT USAGE ON SCHEMA public TO {ROLE};
            GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO {ROLE};
            GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {ROLE};
            """
        )

    class Switch:
        def __enter__(self):
            self.atomic = transaction.atomic()
            self.atomic.__enter__()
            with connection.cursor() as cur:
                cur.execute(f"SET LOCAL ROLE {ROLE}")

        def __exit__(self, *exc):
            return self.atomic.__exit__(*exc)

    return Switch()


def seed(tenant, value):
    writes.apply(tenant.id, [Assert("employee:1", "salary", Span(date(2024, 1, 1)), value)])


def test_scoped_role_sees_only_its_tenant(tenant, other_tenant, as_app_role):
    seed(tenant, 100)
    seed(other_tenant, 999)
    with as_app_role, tenancy.scoped(tenant.id):
        # Deliberately ask for the other tenant: RLS must hide it.
        assert reads.value_at(other_tenant.id, "employee:1", "salary", date(2024, 6, 1)) is None
        assert reads.value_at(tenant.id, "employee:1", "salary", date(2024, 6, 1)) == 100


def test_unscoped_role_sees_nothing(tenant, as_app_role):
    seed(tenant, 100)
    with as_app_role:
        assert reads.committed_version(tenant.id) == 0
        assert reads.value_at(tenant.id, "employee:1", "salary", date(2024, 6, 1)) is None


def test_scoped_role_cannot_write_into_another_tenant(tenant, other_tenant, as_app_role):
    seed(other_tenant, 1)
    with as_app_role, tenancy.scoped(tenant.id), connection.cursor() as cur:
        cur.execute("UPDATE backdate_fact SET value = '0' WHERE tenant_id = %s", [other_tenant.id])
        assert cur.rowcount == 0


def test_scoped_role_can_run_the_write_path(tenant, as_app_role):
    with as_app_role, tenancy.scoped(tenant.id):
        result = writes.apply(
            tenant.id, [Assert("employee:1", "salary", Span(date(2024, 1, 1)), 5)]
        )
        assert result.version == 1


def test_scoped_role_write_to_other_tenant_fails(tenant, other_tenant, as_app_role):
    # The clock row of the other tenant is invisible, so lock_for_write
    # tries to create it and the policy's WITH CHECK refuses.
    op = Assert("e", "a", Span(date(2024, 1, 1)), 1)
    with (
        as_app_role,
        tenancy.scoped(tenant.id),
        pytest.raises(Exception, match="row-level security"),
    ):
        writes.apply(other_tenant.id, [op])


def test_scope_is_reset_after_use(tenant):
    with tenancy.scoped(tenant.id), connection.cursor() as cur:
        cur.execute("SELECT current_setting('backdate.tenant_id', true)")
        assert cur.fetchone()[0] == str(tenant.id)
    with connection.cursor() as cur:
        cur.execute("SELECT current_setting('backdate.tenant_id', true)")
        assert cur.fetchone()[0] == ""
