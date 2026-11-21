# Benchmarks

Every number here comes from `bench/run.py` on one machine, on one day. Raw JSON is in `bench/results/` when you run it yourself. That folder is gitignored, so these tables are the record.

## Setup

| | |
|---|---|
| Machine | Apple Silicon Mac, 10 cores (`platform.processor() = arm`), macOS 27.2 |
| Postgres | 18.7 (Homebrew), same machine, `max_connections=300`, otherwise default config |
| Python | 3.13.15, Django 6.1 |
| Run | 2026-11-21, `uv run python bench/run.py` with defaults |
| Data | 200 employees, 12 months, 2 derivations (gross, withholding) = 4,800 results |

Client, workers and database share one machine, so absolute numbers are optimistic about network latency and pessimistic about CPU. Compare rows with each other, not with production numbers from elsewhere.

## Results

### Write latency

300 single-op backdated raises against a fully computed tenant. Each write runs the full path: clock lock, diff, version bump, fact rows, change ranges, and the invalidation join over read ranges.

| p50 | p95 | p99 | mean | mean results invalidated per write |
|---|---|---|---|---|
| 4.33 ms | 4.84 ms | 7.58 ms | 4.41 ms | 10.5 |

### Initial compute throughput

Drain all 4,800 pending results from an empty start with N worker processes (`backdate_worker --once`, batch 20).

| Worker processes | Seconds | Results/s | Speedup |
|---|---|---|---|
| 1 | 27.10 | 177 | 1.0x |
| 2 | 12.79 | 375 | 2.1x |
| 4 | 9.14 | 525 | 3.0x |

I reran 1 and 2 processes twice more and got 185/374 and 188/374 results/s, so 1 to 2 is steady at about 2x. Going from 2 to 4 processes scales worse. I have not profiled why. Contention on the share lock of the tenant clock during saves is a likely suspect, since all 4,800 results are in one tenant.

### Targeted vs naive recompute after one backdate

One raise effective 1 July for one employee, then wait until every result is fresh again, using 4 worker processes.

- **Targeted** is backdate as built: read ranges decide what is stale.
- **Naive** is the same write followed by marking every result stale, which is what you do when you don't track dependencies.

| | Results recomputed | Write | Time until consistent |
|---|---|---|---|
| Targeted | 12 | 5.75 ms | 0.67 s |
| Naive (recompute all) | 4,800 | | 8.82 s |

The 12 are July to December, gross plus withholding, which is exactly the right set. Both times include starting 4 worker processes, and a single `backdate_worker --once` on an empty queue takes 0.39 s wall time on this machine. Most of the 0.67 s is that startup, not recompute. A long-running worker pool would make the targeted case much faster. The naive case would barely change, since it is dominated by the 4,800 recomputes.

### Clock contention

8 threads, 50 writes each, each thread writing its own entity. The same work either lands in one tenant, where every write queues on one clock row, or in 8 tenants.

| | p50 | p95 | p99 | Writes/s |
|---|---|---|---|---|
| 8 writers, 1 tenant | 22.79 ms | 25.38 ms | 41.21 ms | 349 |
| 8 writers, 8 tenants | 14.15 ms | 17.96 ms | 21.16 ms | 556 |

This is the cost of serializing writes per tenant. The 8-tenant case is not 8x faster because all threads share one Python process (GIL) and one machine. For the reasoning behind accepting this, see [ADR 0001](adr/0001-per-tenant-clock.md).

### Lease recovery

`SIGKILL` a worker mid-compute with `BACKDATE_LEASE_SECONDS=3`, then poll for a claim.

| Lease | Time from kill until the work is redone |
|---|---|
| 3 s | 3.01 s |

Recovery time is the lease length, as designed. A shorter lease recovers faster, but a derivation that legitimately runs longer than the lease will be fenced and redone.

## Not measured yet

- Multiple machines, and a network between app and database.
- Postgres behind pgbouncer in transaction mode.
- Large histories, for example 10 years of daily corrections on one attribute.
- API-level latency through gunicorn (these numbers call the Python functions directly).

## Reproduce

```bash
createdb -p 5433 backdate_bench   # the harness drops and recreates it anyway
uv run python bench/run.py
uv run python bench/run.py --employees 50 --writes 50   # quicker
```
