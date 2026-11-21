# Runbook

## Deploy

1. Postgres 15 or newer (Django 6.1 needs 15+; developed on 18).
2. Create two roles:
   ```sql
   CREATE ROLE backdate_owner LOGIN PASSWORD '...';
   CREATE ROLE backdate_api LOGIN PASSWORD '...' NOSUPERUSER NOBYPASSRLS;
   CREATE DATABASE backdate OWNER backdate_owner;
   ```
3. Run migrations as the owner: `PGUSER=backdate_owner python manage.py migrate`.
4. Grant the API role table access (it is not the owner, so row-level security applies to it):
   ```sql
   GRANT USAGE ON SCHEMA public TO backdate_api;
   GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO backdate_api;
   GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO backdate_api;
   ```
5. Start the API as `backdate_api` and the workers as `backdate_owner`:
   ```bash
   gunicorn server.wsgi -w 4 -b 0.0.0.0:8000
   python manage.py backdate_worker
   ```
6. Required env in production: `BACKDATE_ENV=production`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `PG*`. See `server/settings.py` for the rest; every default there is for development.

Do not put the API behind pgbouncer in transaction mode as-is. The tenant setting for row-level security is per session. See ADR 0006.

## Tenants and keys

```bash
python manage.py create_tenant acme --name "Acme Ltd"              # prints a key once
python manage.py create_tenant acme --scopes read --label grafana  # another key, read only
```

Revoke a key with its prefix, the part between `bk_` and the second `_`:

```sql
UPDATE backdate_apikey SET revoked_at = now() WHERE prefix = '<prefix>';
```

## What to watch

| Signal | Healthy | Act when |
|---|---|---|
| `backdate_computations{status="stale"}` + `pending` | Returns to near zero after each burst of writes | Climbs for longer than your recompute SLO |
| `backdate_computations{status="failed"}` | 0 | Any increase |
| `rate(backdate_computations_total{outcome="fenced"})` | Near 0 | Sustained: lease too short for some derivation |
| `rate(backdate_computations_total{outcome="requeued"})` | Small | High and steady: the same facts are written constantly |
| `backdate_write_seconds` p99 | Tens of ms | Hundreds of ms: clock contention or a slow invalidation join |
| `/readyz` | 200 | 503 |

## Incidents

**Backlog is growing.**
1. Is anything running? `ps` for `backdate_worker`, or check `lease_owner` on pending rows.
2. Are workers failing? `GET /v1/computations?status=failed` and read `last_error`.
3. Add worker processes. Throughput scaled about 3x from 1 to 4 workers on one machine (see benchmarks).
4. If writes are being refused with 503, that is backpressure doing its job. Raise `BACKDATE_MAX_STALE_BACKLOG` only if readers can live with staler results for longer.

**A derivation is failing.**
1. Read `last_error` on the failed rows.
2. Fix and deploy the code, then bump its `version=` in `@derivation`.
3. `python manage.py backdate_rebase <name>` marks fresh results from older code stale. Failed rows also need `UPDATE backdate_computation SET status='stale', attempts=0 WHERE derivation='<name>' AND status='failed';`.

**The feed has stopped moving.**
A long transaction is holding back xmin.
```sql
SELECT pid, now() - xact_start AS age, state, query
  FROM pg_stat_activity
 WHERE xact_start IS NOT NULL ORDER BY xact_start LIMIT 5;
```
End the offender. Nothing is lost; rows appear once it finishes.

**Writes in one tenant are slow.**
Writes queue on that tenant's clock row. Look for a long transaction holding it:
```sql
SELECT pid, now() - xact_start, query FROM pg_stat_activity
 WHERE wait_event_type = 'Lock' OR query ILIKE '%tenantclock%';
```

**A worker host died.**
Nothing to do. Its claims become available after `BACKDATE_LEASE_SECONDS`.

## Backups and restore

Everything is in Postgres. Use your normal base backup plus WAL archiving. After a point-in-time restore, run workers as usual. Any computation that was mid-lease at the restore point has an old lease that will expire.
