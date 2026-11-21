# Research notes

Written 2026-11-21. Links were checked on that date. Where a source did not say something, these notes don't claim it.

## The problem

Payroll, billing and HR systems all store facts that are true *for a period*: a salary from 1 March, a tax rate for a quarter, a plan price until a renewal. Those facts get corrected after the fact. Someone enters a raise in May that should have started in March, and every number computed from March onwards is now wrong.

The big payroll vendors treat this as a first-class workflow, usually called retro pay:

- Workday has a dedicated "process retroactive payroll" flow ([docs](https://doc.workday.com/admin-guide/en-us/payroll/retroactive-payroll/process-retroactive-payroll/dan1370797357965.html)).
- SAP SuccessFactors Employee Central has settings to limit how far back changes may reach ([community post](https://community.sap.com/t5/human-capital-management-blog-posts-by-members/controlling-retroactive-payroll-data-changes-in-employee-central/ba-p/14481423)).
- Oracle HCM documents how retroactive changes are picked up by its payroll interface ([docs](https://docs.oracle.com/en/cloud/saas/human-resources/oapnt/how-retroactive-changes-for-payroll-interface-are-extracted.html)).

The underlying need has two parts:

1. Store facts with two time axes: when the fact is true (valid time), and when the system learned it (knowledge or transaction time). This is the classic bitemporal model. [Aiven's write-up](https://aiven.io/blog/two-dimensional-time-with-bitemporal-data) and [Aerospike's](https://aerospike.com/blog/bitemporal-data/) both cover it.
2. When a past fact changes, find exactly which derived numbers depended on it, recompute only those, and publish the difference as a correction. A ledger downstream can then post the delta. It doesn't have to diff whole payrolls.

The first part is well covered by databases now. The second part is where teams write bespoke code, and it is where the bugs live: a recompute that misses a dependency, two workers racing on the same result, a correction published twice.

## What exists

**Postgres.**
- Postgres 18 added temporal constraints: `WITHOUT OVERLAPS` on primary keys and unique constraints, and `PERIOD` on foreign keys ([release notes](https://www.postgresql.org/about/news/postgresql-18-released-3142/), [feature matrix](https://www.postgresql.org/about/featurematrix/detail/temporal-constraints/), [Hashrocket walkthrough](https://hashrocket.com/blog/posts/postgresql-18-temporal-constraints)).
- `UPDATE/DELETE ... FOR PORTION OF` was committed for Postgres 19 ([depesz, 2026-04-02](https://www.depesz.com/2026/04/02/waiting-for-postgresql-19-add-update-delete-for-portion-of/)) and later reverted before release ([Snowflake engineering blog, 2026-09-16](https://www.snowflake.com/en/blog/engineering/postgresql-19-release-delay-feature-reverts/)). That post says most reverted features will be tried again in v20 but gives no date for this one.
- So today the database will stop you storing overlapping rows, but splitting a row when you change the middle of its range is still application code.

**Django.**
- Ticket [#36627](https://code.djangoproject.com/ticket/36627), "Support PostgreSQL 18+ temporal constraints", was opened 2025-09-26 and closed 2025-09-29 as `needsnewfeatureprocess`. Primary key and foreign key support were called out as the hard parts. Django can express the overlap rule with `ExclusionConstraint` over a range field, which is what backdate uses.
- [django-pghistory](https://github.com/ambitioneng/django-pghistory/blob/629ace9eed6461b160f55ba3a5cab2b339dd8e5b/docs/index.md) tracks row history with triggers. That records when a row changed (transaction time). It does not model when a value is effective, and it does not track derived values.
- [django_temporal](https://github.com/zejn/django_temporal/blob/master/Documentation.md) did model valid time, but its own docs talk about Django 1.7 limits. It is not something to build on in 2026.

**Incremental recomputation.** Materialized view maintenance (pg_ivm, Materialize, Differential Dataflow) handles "inputs changed, update outputs". It works on SQL views over tables, though. Payroll rules are Python code with proration, rounding and lookups that read different dates depending on earlier lookups, and those are hard to express as a view.

## Gap

Nothing I found gives a Django app on Postgres all of these together:

- effective-dated facts with full history of what was known when,
- derived values written as ordinary Python,
- automatic tracking of which fact ranges each derived value read,
- invalidation in the same transaction as the fact change, so a fresh-looking stale value is never visible,
- recompute workers that survive crashes and races without double-publishing,
- an append-only feed of corrections with deltas.

## Candidates considered

Three ideas fit the brief: hard, relevant to payroll, payments or observability companies, and buildable on Django + Postgres. I also checked existing projects in `~/dev` so this would not repeat one of them.

**A. backdate.** Bitemporal facts plus retroactive recomputation, as described above.

**B. A webhook delivery service with exactly-once effects.** A transactional outbox, signed deliveries, per-endpoint ordering, retry with backoff, endpoint health and a replay UI. Stripe-shaped. This is well-trodden: Svix and Hookdeck exist, and the outbox pattern is widely written up. The hard part is mostly operational. There is little new algorithmic ground.

**C. A fair-share job queue on Postgres.** A multi-tenant queue on `SKIP LOCKED`, with weighted fair scheduling across tenants, rate limits and priority, so one noisy tenant cannot starve the rest. Relevant to anyone running shared workers. It is interesting, but procrastinate and other Postgres queues already cover the base, so the novel part is a scheduling policy. That is thin for a whole project.

Scores are 1 to 10, my judgement, higher is better:

| Criterion | A backdate | B webhooks | C fair queue |
|---|---|---|---|
| Real problem at target companies | 9 | 8 | 7 |
| Not already solved by a library | 9 | 4 | 5 |
| Correctness depth (races, crashes, consistency) | 10 | 7 | 7 |
| Uses Postgres seriously | 9 | 6 | 8 |
| Testable with strong oracles | 9 | 6 | 6 |
| Benchmarkable with honest numbers | 8 | 7 | 8 |
| Explainable in an interview in 5 minutes | 8 | 9 | 8 |
| Fits a laptop (no cluster needed) | 9 | 8 | 9 |
| Different from my existing projects | 9 | 6 | 6 |
| **Total** | **80** | **61** | **64** |

A wins mainly on two counts. Nobody ships it for Django, and it has a clean oracle: recompute everything from scratch and compare. A strong oracle is what makes deep tests possible.

## Scope limits set before building

- Dates, not timestamps, for valid time. Payroll and billing are day-grained. Sub-day validity is a roadmap item.
- One Postgres primary. No sharding. Tenants are the unit of write serialization, and the benchmark measures that ceiling.
- Derivations are synchronous Python functions. No async and no external calls inside a derivation, because they would break determinism.
- Light compute: the full test suite and benchmark run on a laptop CPU in minutes.
