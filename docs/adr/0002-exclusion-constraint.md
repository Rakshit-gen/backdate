# 0002: Exclusion constraint instead of WITHOUT OVERLAPS

Status: accepted, 2026-11-21

## Context

Postgres 18 can say "no overlapping periods per key" with `UNIQUE (..., valid WITHOUT OVERLAPS)`. Older versions, and Django, express the same rule with `EXCLUDE USING gist (... WITH =, valid WITH &&)`.

backdate needs the rule only for rows currently believed (`tx_to IS NULL`). Superseded rows overlap by design.

## Decision

Use `ExclusionConstraint` with `condition=Q(tx_to__isnull=True)`.

## Why

- `WITHOUT OVERLAPS` belongs to `UNIQUE` and `PRIMARY KEY` constraints, which cannot carry a `WHERE` clause. A unique *index* can be partial, but `WITHOUT OVERLAPS` is a constraint feature. The partial exclusion constraint says exactly what we mean.
- Django supports `ExclusionConstraint` today. Support for temporal constraints was proposed in [ticket #36627](https://code.djangoproject.com/ticket/36627) and closed as needing the new-feature process, so there is no Django API for it yet.
- It works on any Postgres that Django 6.1 supports, not only 18.

## Consequences

- Needs `btree_gist` for the scalar columns. Migration 0001 installs it.
- The GiST index serves both the constraint and the "current rows of this attribute" lookup in the write path.
