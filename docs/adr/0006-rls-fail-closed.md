# 0006: Row-level security as a fail-closed backstop

Status: accepted, 2026-11-21

## Context

Every query filters by `tenant_id`, taken from the API key. One forgotten filter in a new endpoint would leak another tenant's payroll.

## Decision

Enable RLS on every tenant-scoped table with
`USING (tenant_id = NULLIF(current_setting('backdate.tenant_id', true), '')::bigint)`.
The API sets the value per request and clears it afterwards. The API should connect as a role that does not own the tables. Workers and migrations connect as the owner, which bypasses RLS, because a worker serves every tenant.

## Consequences

- If the setting is missing, the comparison is against NULL and no rows match. Forgetting to scope fails closed.
- `set_config(..., false)` is session-level, so the middleware resets it in a `finally`. With connection pooling in transaction mode (pgbouncer), session settings are not safe at all. Switch to `set_config(..., true)` inside an explicit per-request transaction before deploying behind one. This is noted in the runbook.
- Only effective if the API's database role is not the owner and not a superuser. The tests check it under such a role. Local development as a superuser gets no protection from it.
