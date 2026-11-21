# 0004: Track reads as date ranges, not rows

Status: accepted, 2026-11-21

## Context

To invalidate precisely we need to know what each result depended on. The candidates are fact row ids, `(entity, attribute)` pairs, or `(entity, attribute, date range)`.

## Decision

`(entity, attribute, date range)`. A derivation reads through `ctx.timeline(entity, attribute, span)` or `ctx.value_at(...)`, and the context records the span. Spans per attribute are merged before saving, so a month of daily lookups becomes one row.

## Why

- **Row ids are wrong.** A write that splits a row creates new ids, and a backdated insert into a gap has no old row to point at. The dependency is on *the value over that period*, whatever rows hold it.
- **Whole attributes are too coarse.** A salary change in July would restate January.
- **Ranges match what writes produce.** A write records exactly the spans whose values changed (`changerange`), and the invalidation is a GiST `&&` join between the two.

## Consequences

- A derivation that reads outside `ctx` (raw ORM, other tables, the wall clock) has untracked dependencies and will not be invalidated. The registry docstring says so. There is no way to enforce it from Python.
- Read ranges are replaced on every save, so the read set always reflects the latest run, including reads that only happen on some branches.
