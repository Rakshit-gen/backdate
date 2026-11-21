# Self-review: questions I would ask as the interviewer

Answers are what I would actually say, including the parts I'm not proud of.

## 1. What is the hardest bug this design prevents, and how do you know it works?

Lost invalidation. A worker reads at version 7 and computes. A write at version 8 changes something it read and commits. Then the worker saves its version-7 answer as fresh. Nothing would ever recompute it, and payroll for that month would be quietly wrong forever.

The fix is the save protocol. Take the clock `FOR SHARE`, which waits out any in-flight writer. Then check for change ranges newer than the read version that overlap the read set, and requeue if there are any. I know it works in three ways:

- `test_races.py` reproduces the exact interleaving step by step.
- `test_concurrency.py::test_saver_blocks_behind_in_flight_writer` shows the save really blocks behind a writer holding the clock.
- `test_no_lost_invalidation_under_concurrent_writes_and_workers` runs writers and workers on threads, then compares every result with a from-scratch recompute.

What I don't have is a model-checked proof (TLA+). The argument is in `architecture.md`, and the tests are the evidence.

## 2. Why serialize writes per tenant? Isn't that a bottleneck?

Yes, it's a ceiling, and I measured it: 349 writes/s with 8 writers in one tenant versus 556 across 8 tenants, on one machine. I accepted it because it gives dense, in-order versions. That makes "read at version N" repeatable without snapshot arithmetic, and it gives the save protocol a single thing to wait on. Payroll and billing writes are rare compared to reads and recomputes. If a tenant outgrew it, I'd move that tenant to xid-based versions (ADR 0001), not shard the clock.

## 3. Why not use materialized views or a stream processor?

Payroll rules are code: proration by day, rounding rules, branches that pick which date to read based on earlier reads. Incremental view maintenance wants SQL. A stream processor needs a second system and still needs the bitemporal store. backdate keeps derivations as plain Python and tracks what they read.

## 4. What happens if a derivation reads something outside `ctx`?

It silently goes stale. This is the biggest sharp edge, and nothing in the code stops it. Python can't sandbox the ORM in a way that would be worth the cost. Mitigations would be a lint rule that flags ORM imports in derivation modules, or a debug mode that wraps the connection and fails on queries that don't go through `ctx`. Neither exists yet. It is listed in failure-modes.md.

## 5. How do you avoid deadlocks?

One lock order: tenant clock first. Claims touch only computation rows, with `SKIP LOCKED`, so they never wait. A save locks its own row, then its sources `FOR SHARE` in id order. When a save marks dependents stale it uses `SKIP LOCKED`. A locked dependent is mid-save and will re-check this source's seq anyway. I found that last one by reasoning about two savers in opposite directions, before I wrote the code. No test has deadlocked, but the tests only show the cases I thought of.

## 6. What did the benchmark tell you that you didn't expect?

Two things:

- Scaling from 2 to 4 worker processes gives about 1.4x, not 2x. I haven't profiled it. My guess is the share lock on the single tenant clock during saves, since the whole bench is one tenant. That guess is the next thing to test, by spreading the same work over several tenants.
- Most of the 0.67 s targeted recompute time is worker process startup (0.39 s), not computing. The benchmark spawns workers per scenario, which flatters the naive baseline less than it hurts the targeted case. A persistent worker pool is on the roadmap.

## 7. How would this fail in production first?

Probably one of two ways:

- A long transaction somewhere holds back `xmin` and the restatement feed stalls. Nothing is lost, but consumers see lag and think it's broken. The runbook has the query.
- A derivation that sometimes runs longer than the lease gets fenced, redone, fenced again. That shows up as a rising `fenced` counter. Fixing it needs a per-derivation lease or a heartbeat that extends the lease, and neither exists.

## 8. What would you cut if you had half the time?

- Row-level security. Application-level filtering plus the isolation tests is the core. RLS is a backstop.
- Dependencies between derived results. Withholding could re-read the gross inputs directly. It would duplicate work, but it would remove `DerivedRead`, the recursive invalidation walk and the seq check.

I'd keep the exclusion constraint, the save protocol and the model-based test. Without those the project doesn't mean anything.

## 9. What's untested or weak?

- `compose.yaml` and the Dockerfile have never run on my machine (no Docker locally). CI builds the image but doesn't start it.
- No API latency numbers through gunicorn. The benches call Python functions directly.
- No test with a real network between app and database, and none behind pgbouncer.
- The RLS setting is session-level, which breaks under transaction pooling. That's documented, not fixed.
- The bench is single-machine. Absolute numbers will differ on real hardware.

## 10. If this were going into Rippling's payroll tomorrow, what would you add first?

- Audit: who changed what and why is already on `Changeset`. It needs an API and retention rules.
- Approval: a write that would restate a closed pay period should need a second person, which is a state on the changeset before it applies.
- Per-tenant fair claiming, so one company's bulk backdate can't starve everyone else's workers.
- A dry run: "what would this backdate change?". It's the same read-set join without the commit, and it's probably what payroll admins want most.
