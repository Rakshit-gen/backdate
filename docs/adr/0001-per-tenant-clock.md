# 0001: Serialize writes per tenant with a clock row

Status: accepted, 2026-11-21

## Context

Reads need a version that means "everything up to here". If version 9 could commit before version 8, a reader at version 9 could miss version 8's rows. The answer at version 9 would then change once version 8 landed, and "read at version N" would not be repeatable.

The save protocol also needs a point where it can say "every write that will ever get a version at or below the current one has committed".

## Options

1. **A sequence for versions, no lock.** Fast, but versions are handed out at call time and commit in any order. Readers would have to compute a safe version from running transactions, and the save check would need the same logic.
2. **Version from the transaction id (`xid8`) plus `pg_snapshot_xmin`.** No serialization of writes. Readers use "every xid below the snapshot's xmin". This works, but versions become sparse, global across tenants, and hard to explain to a user ("as of version 7418823"). It also makes the save check depend on snapshot internals.
3. **One clock row per tenant, held `FOR UPDATE` until commit.** Versions are dense, per tenant and in commit order. Saves take it `FOR SHARE` to wait out writers.

## Decision

Option 3.

## Consequences

- Writes within a tenant run one at a time. Measured on a laptop: 349 writes/s with 8 writers in one tenant versus 556 spread over 8 tenants ([benchmarks](../benchmarks.md#clock-contention)). That is a ceiling of a few hundred writes per second per tenant. For payroll or billing, writes are rare compared to reads and computes, so that is fine. It would not be fine for a per-event stream.
- A long write transaction blocks other writes, and saves, in that tenant. `statement_timeout` and `idle_in_transaction_session_timeout` are set in settings to bound this.
- If one tenant ever needs more, the next step is option 2 for that tenant, not sharding the clock.
