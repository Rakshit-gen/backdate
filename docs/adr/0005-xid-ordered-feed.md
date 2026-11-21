# 0005: Page the restatement feed by transaction id

Status: accepted, 2026-11-21

## Context

Consumers poll the feed with a cursor and must never skip a row. A `bigserial` id is assigned at insert, but the row becomes visible at commit. Transaction A takes id 10, transaction B takes id 11 and commits first. A consumer reading "after 9" sees 11, moves its cursor to 11, and never sees 10.

## Options

1. **Feed from a separate table filled by one serialized writer.** Simple to reason about, but every save would contend on it.
2. **Logical decoding or an outbox relay.** Correct, but it is a second moving part to deploy and monitor.
3. **Order by the inserting transaction's id, and hide rows from transactions newer than the oldest one still running.**

## Decision

Option 3. Each restatement stores `pg_current_xact_id()` at insert. The feed returns rows with `txid < pg_snapshot_xmin(pg_current_snapshot())`, ordered by `(txid, id)`. The cursor is the last `(txid, id)` seen.

## Consequences

- A row becomes visible to the feed only after every transaction older than it has finished. A long-running unrelated transaction delays the feed. It does not lose rows. The `idle_in_transaction_session_timeout` setting limits the damage.
- Transaction ids are 64-bit (`xid8`), so wraparound is not a concern.
- `tests/test_api.py` checks both directions: rows from an open transaction stay hidden, and paging with a small limit returns every row exactly once.
