# Failure modes

What breaks, what happens, and how you would notice. "Tested" points at the test that does it on purpose.

| Failure | What happens | Data safe? | How you notice | Tested |
|---|---|---|---|---|
| Worker SIGKILLed mid-compute | Lease stays until it expires, then another worker claims it with a new token. A late save from the dead worker is fenced. | Yes | `backdate_computations{status="pending"}` stays flat for one lease period | `test_crash.py::test_sigkilled_worker_lease_expires_and_work_is_redone` |
| Worker SIGTERMed | Finishes the current batch and exits 0. | Yes | Log line `worker ... stopped` | `test_crash.py::test_sigterm_finishes_cleanly` |
| DB connection dies during save | Save transaction rolls back. The row is claimable after its lease. No restatement. | Yes | Worker logs an `OperationalError` | `test_crash.py::test_connection_lost_during_save_leaves_row_claimable` |
| Writer's backend killed mid-write | Transaction rolls back. The clock is not advanced, so the next write takes the next version. | Yes | Client sees a 500 or a connection error and retries with the same `Idempotency-Key` | `test_crash.py::test_writer_killed_mid_transaction_leaves_no_trace` |
| Write lands while a result is computing | The save sees a newer change range over its reads and requeues. | Yes | `backdate_computations_total{outcome="requeued"}` | `test_races.py`, `test_concurrency.py` |
| Source result changes while a dependent computes | The dependent's save sees the source's seq moved and requeues. | Yes | Same counter | `test_races.py::test_dependent_save_rejected_when_source_moved` |
| Client retries a write | Same key and body: the stored response is replayed with `Idempotent-Replayed: true`. Same key, different body: 409. | Yes | Header on response | `test_idempotency.py`, `test_api.py` |
| Client resends a write without a key | The diff finds nothing to change: no version, no invalidation. | Yes | `noop: true` in the response | `test_writes.py::test_noop_write_spends_no_version` |
| Derivation raises | Retries with backoff (1s, 2s, 4s ... capped at 5 min) up to `BACKDATE_MAX_ATTEMPTS`, then `failed` with `last_error`. A later write touching its reads resets it to stale. | Yes | `status=failed` rows, `outcome="failed"` counter | `test_derive_flow.py::test_failing_derivation_backs_off_then_fails` |
| Derivation reads outside `ctx` | Its result will not be invalidated when that data changes. | **No**, silently stale | Nothing automatic. Code review. | Not testable from inside; see ADR 0004 |
| Derivation is not deterministic | Recomputes publish restatements with no real change. | Feed noise | Restatements with a zero or odd `delta` | n/a |
| Derivation code changes | Old results stay as they were until `backdate_rebase <name>` marks them stale. | Yes | `code_version` column differs from the registry | n/a |
| Backlog explodes (bulk backdate) | New writes get 503 and `Retry-After` past `BACKDATE_MAX_STALE_BACKLOG`. | Yes | `backdate_computations{status="stale"}`, 503 rate | `test_api.py::test_backpressure_returns_503_with_retry_after` |
| Long-running transaction anywhere | Feed delivery stalls (rows wait for xmin to pass them). Writers in that tenant wait if it holds the clock. | Yes | Feed lag; `pg_stat_activity` | `test_api.py::test_feed_hides_rows_from_open_transactions` |
| Lease shorter than a slow derivation | The derivation is fenced off at save and redone by someone else, possibly forever. | Yes, but wasted work | Rising `outcome="fenced"` | `test_races.py::test_expired_lease_is_fenced_off` |
| Postgres down | API returns 500 and `/readyz` 503. Workers error on claim and retry on the next loop. | Yes | `/readyz` | Readiness covered in `test_api.py` |
| Missed tenant filter in new code | Under a non-owner role, RLS returns no rows. | Yes, if deployed as documented | Empty responses | `test_rls.py` |
| API key leaked | Full access to that tenant within the key's scopes. | No | n/a | Revoke: set `revoked_at` (see runbook) |

## Known gaps

- No automatic detection of reads outside `ctx`.
- No per-derivation timeout inside a worker. A derivation that hangs holds its worker until the process is killed. Run workers under a supervisor that restarts them.
- No dead-letter view beyond `status=failed`. The API can list them with `?status=failed`.
