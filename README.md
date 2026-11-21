# backdate

Bitemporal facts for Django on Postgres, with retroactive recomputation of everything derived from them.

You store facts that are true over a date range: a salary from 1 March, a tax rate for a quarter. You write derived values as plain Python functions: gross pay for March, tax withheld for March. When someone corrects a fact in the past, backdate works out exactly which derived values read the changed dates. It marks them stale in the same transaction, recomputes them on workers, and publishes each change as a correction with a delta that a ledger can post.

Real output from the quick start below (20 seeded employees), after backdating a raise for employee 7 to 1 March:

```
POST /v1/writes  {"ops": [{"op": "assert", "entity": "employee:7",
                           "attribute": "annual_salary_cents",
                           "from": "2024-03-01", "value": 7300000}]}
{"version": 3, "noop": false, "invalidated": 20, ...}

GET /v1/restatements   (after one worker pass)
payroll.gross 7:2024-03  gross_cents 49973  -> 64000   delta +14027   (4 days paid, hired late March)
payroll.gross 7:2024-05  gross_cents 387288 -> 496000  delta +108712
payroll.gross 7:2024-06  gross_cents 374795 -> 480000  delta +105205
...
```

20 results were invalidated: gross and withholding for March to December. January and February weren't touched.

## Why

Retro pay is a standard workflow in payroll products (Workday, SAP and Oracle all document one). The storage half is now easy in Postgres. The hard half is knowing what to recompute, and recomputing it without races. That part usually ends up as bespoke code with subtle bugs. [docs/research.md](docs/research.md) has the survey and sources.

## What it guarantees

- **Repeatable reads at any past version.** Ask what the salary was on 15 March *as the system knew it at version 30*, and you get the same answer forever.
- **No overlapping truths.** A Postgres exclusion constraint makes sure an attribute has at most one current value per day.
- **No fresh-looking stale results.** Invalidation commits with the write that caused it.
- **No lost invalidations.** A result computed from facts that changed while it was computing is thrown away, never saved. ([why](docs/architecture.md#why-no-invalidation-is-lost))
- **No zombie writers.** Each claim carries a fencing token. A worker whose lease expired cannot save.
- **One correction per real change.** Re-saving an identical result publishes nothing, and a write that changes nothing spends no version.
- **A feed that never skips.** The correction feed pages by transaction id, so rows that commit out of order are not missed.
- **Tenant isolation twice.** Every query filters by tenant, and Postgres row-level security backs that up for the API role.

## Quick start

Needs Python 3.12+, [uv](https://docs.astral.sh/uv/) and Postgres 15+ (developed on 18).

```bash
uv sync
createdb backdate            # defaults: localhost:5433, see .env.example
uv run python manage.py migrate
TOKEN=$(uv run python manage.py create_tenant demo)
uv run python manage.py seed_payroll demo --employees 20
uv run python manage.py backdate_worker --once
uv run python manage.py runserver
```

```bash
curl -s localhost:8000/v1/clock -H "Authorization: Bearer $TOKEN"
curl -s -X POST localhost:8000/v1/writes -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -H "Idempotency-Key: raise-7" \
  -d '{"reason":"raise","ops":[{"op":"assert","entity":"employee:7",
       "attribute":"annual_salary_cents","from":"2024-03-01","value":7300000}]}'
```

There is also a `compose.yaml` with Postgres, the API and two workers. I have not run it myself (there is no Docker on my machine), but CI builds the image.

## Writing a derivation

```python
from backdate.derive.registry import derivation

@derivation("payroll.gross", version="1")
def gross(ctx, key):
    entity, month = parse_key(key)                   # "7:2024-03"
    salary = ctx.timeline(entity, "annual_salary_cents", month)
    fte = ctx.timeline(entity, "fte_bp", month)
    ...
    return {"gross_cents": cents, "days_paid": days}
```

Read facts only through `ctx`. That is how backdate learns what the result depends on. `ctx.derived("other.derivation", key)` reads another result and records that dependency too. Anything else a derivation reads is invisible to invalidation. Bump `version=` when the logic changes, then run `manage.py backdate_rebase payroll.gross`.

## API

All under `/v1/`, authenticated with `Authorization: Bearer bk_...`. Keys have `read`, `write` and `compute` scopes.

| Method | Path | |
|---|---|---|
| POST | `/writes` | Apply assert and retract ops. Supports `Idempotency-Key`. Returns 503 with `Retry-After` when the backlog is over the limit. |
| GET | `/facts/<entity>/<attribute>?version=&from=&to=` | Timeline as known at a version |
| GET | `/facts/<entity>/<attribute>/history` | Every row ever believed, with `tx_from`/`tx_to` |
| GET | `/entities/<entity>?on=YYYY-MM-DD&version=` | All attributes on one day |
| GET | `/changesets?after_version=` | What each version changed |
| GET | `/clock` | Current version and computation counts by status |
| GET | `/derivations` | Registered derivations |
| GET, POST | `/computations` | List with filters, or request `{derivation, keys}` |
| GET | `/computations/<id>` | Result, lease, read set, dependencies, restatements |
| GET | `/restatements?cursor=` | The correction feed |

Plus `/healthz`, `/readyz` and `/metrics` (Prometheus).

## Tests

```bash
uv run pytest            # 150 tests, about 15 s, needs Postgres
```

The tests that do the most work:

- `test_model_based.py`: a Hypothesis state machine. It writes random backdated changes and checks reads at *every past version* against an in-memory model.
- `test_concurrency.py`: writer and worker threads run together, then every result is checked against a from-scratch recompute.
- `test_races.py`: the lost-invalidation, fencing and dependency races, driven step by step.
- `test_crash.py`: `SIGKILL` a worker process, `pg_terminate_backend` a writer and a saver.
- `test_rls.py`: tenant isolation checked as a non-owner database role.

## Numbers

From `bench/run.py` on one Apple Silicon Mac with Postgres 18 on the same machine. Full table and caveats in [docs/benchmarks.md](docs/benchmarks.md).

| | |
|---|---|
| Backdated write, p50 / p99 | 4.33 ms / 7.58 ms |
| Recompute throughput, 1 / 4 worker processes | 177 / 525 results/s |
| One backdated raise, results recomputed: targeted vs everything | 12 vs 4,800 |
| Time until consistent: targeted vs everything (4 workers, incl. ~0.4 s worker startup) | 0.67 s vs 8.82 s |
| 8 concurrent writers, one tenant vs eight | 349 vs 556 writes/s |

## Docs

- [Architecture](docs/architecture.md): data model, write and save protocols, lock order, the feed
- [Decisions](docs/adr/): per-tenant clock, exclusion constraint, requeue, range read sets, xid feed, RLS
- [Failure modes](docs/failure-modes.md) and the tests that cover each one
- [Runbook](docs/runbook.md): deploy, roles, alerts, incidents
- [Benchmarks](docs/benchmarks.md)
- [Research](docs/research.md)
- [Interview self-review](docs/interview-review.md)

## Limits and roadmap

- Valid time is day-grained. Timestamps would mean `tstzrange` and a second set of span helpers.
- Writes in one tenant are serialized. That ceiling is a few hundred writes/s per tenant on one machine. It is fine for payroll and billing, not for event streams. An xid-based clock is the escape hatch ([ADR 0001](docs/adr/0001-per-tenant-clock.md)).
- No per-derivation timeout inside a worker. Run workers under a supervisor.
- Row-level security uses a session setting, so pgbouncer in transaction mode needs the transaction-local variant first.
- Next up: a long-running worker pool with prefetch, `FOR PORTION OF` once Postgres ships it, and per-tenant fair claiming so one big backdate cannot starve other tenants.

## License

Apache-2.0
