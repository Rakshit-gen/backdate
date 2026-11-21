"""Row-level security as a second line of tenant isolation.

Every query in the app already filters by tenant. These policies make a
missed filter return nothing instead of another tenant's rows, for any
role that is not the table owner. Deploy the API under such a role
(see docs/runbook.md). Workers and migrations run as the owner, which
bypasses RLS, because a worker serves every tenant.

The setting is read with missing_ok, so a connection that never set it
sees no rows at all. Fail closed.
"""

from django.db import migrations

TABLES = [
    "backdate_tenantclock",
    "backdate_changeset",
    "backdate_changerange",
    "backdate_fact",
    "backdate_computation",
    "backdate_readrange",
    "backdate_restatement",
    "backdate_idempotencyrecord",
]

POLICY = "NULLIF(current_setting('backdate.tenant_id', true), '')::bigint"


def forwards() -> list[str]:
    out = []
    for t in TABLES:
        out.append(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        out.append(
            f"CREATE POLICY tenant_isolation ON {t} "
            f"USING (tenant_id = {POLICY}) WITH CHECK (tenant_id = {POLICY})"
        )
    return out


def backwards() -> list[str]:
    out = []
    for t in TABLES:
        out.append(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
        out.append(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
    return out


class Migration(migrations.Migration):
    dependencies = [("backdate", "0001_initial")]

    operations = [migrations.RunSQL(forwards(), backwards())]
