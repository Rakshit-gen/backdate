# 0003: Requeue a result that went stale while it was computing

Status: accepted, 2026-11-21

## Context

A worker computes at version 7. Before it saves, version 8 changes something it read. Its answer is correct *for version 7*.

## Options

1. **Save it anyway, with result_version 7, then mark it stale.** The feed would carry a restatement for version 7, then another for version 8 right after. Consumers would post two corrections where one would do, and the intermediate one was never true at any time a reader could see it as current.
2. **Throw it away and requeue.** One restatement, at the version that is current when it finally saves.

## Decision

Option 2.

## Consequences

- Under a steady stream of writes to the same facts, a result can keep missing its save. Each retry rereads at the newest version, so it settles once writes pause. The attempt counter is not charged for this, so it never ends up `failed` just because the data is busy.
- The feed only ever holds results that were current when saved.
