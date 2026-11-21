"""Threads against a real Postgres. Each thread gets its own connection."""

from __future__ import annotations

import random
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from itertools import pairwise

import pytest
from django.db import connections, transaction

from backdate import clock, reads, writes
from backdate.derive import registry, worker
from backdate.derive.context import Context
from backdate.derive.save import SaveOutcome, save
from backdate.intervals import Span
from backdate.models import ChangeRange, Changeset, Computation, Fact, Restatement
from backdate.writes import Assert

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.slow]
D = date


def in_thread(fn):
    def wrapped(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        finally:
            connections.close_all()

    return wrapped


def test_concurrent_writers_get_gap_free_versions(tenant):
    @in_thread
    def write(i):
        span = Span(D(2024, 1, 1 + i % 28))
        return writes.apply(tenant.id, [Assert(f"e{i % 5}", "a", span, i)]).version

    with ThreadPoolExecutor(16) as pool:
        versions = list(pool.map(write, range(100)))

    spent = set(versions)
    changesets = sorted(Changeset.objects.filter(tenant=tenant).values_list("version", flat=True))
    assert changesets == list(range(1, len(changesets) + 1))
    assert spent <= set(changesets) | {0}
    assert reads.committed_version(tenant.id) == len(changesets)


def test_concurrent_writes_to_one_attribute_never_overlap(tenant):
    @in_thread
    def write(i):
        rng = random.Random(i)
        start = D(2024, rng.randint(1, 12), rng.randint(1, 28))
        writes.apply(tenant.id, [Assert("e", "a", Span(start), i)])

    with ThreadPoolExecutor(16) as pool:
        list(pool.map(write, range(80)))

    current = [
        Span.from_range(v)
        for v in Fact.objects.filter(tenant=tenant, tx_to__isnull=True).values_list(
            "valid", flat=True
        )
    ]
    current.sort()
    for a, b in pairwise(current):
        assert not a.overlaps(b)


def test_saver_blocks_behind_in_flight_writer(tenant):
    writes.apply(
        tenant.id,
        [
            Assert("employee:1", "annual_salary_cents", Span(D(2024, 1, 1)), 36_500_00),
            Assert("employee:1", "fte_bp", Span(D(2024, 1, 1)), 10_000),
        ],
    )
    worker.request(tenant.id, "payroll.gross", ["1:2024-03"])
    (claim,) = worker.claim("w", tenant_id=tenant.id)
    ctx = Context(tenant.id, reads.committed_version(tenant.id))
    result = registry.get("payroll.gross").fn(ctx, claim.key)

    writer_has_lock = threading.Event()
    release_writer = threading.Event()
    outcome: list[SaveOutcome] = []

    @in_thread
    def slow_writer():
        with transaction.atomic():
            base = clock.lock_for_write(tenant.id)
            writer_has_lock.set()
            release_writer.wait(5)
            version = clock.advance(tenant.id, base)
            cs = Changeset.objects.create(tenant=tenant, version=version)
            span = Span(D(2024, 3, 15))
            ChangeRange.objects.create(
                tenant=tenant,
                changeset=cs,
                version=version,
                entity="employee:1",
                attribute="fte_bp",
                valid=span.to_range(),
            )

    @in_thread
    def saver():
        outcome.append(save(claim, ctx, result, "1"))

    w = threading.Thread(target=slow_writer)
    w.start()
    assert writer_has_lock.wait(5)
    s = threading.Thread(target=saver)
    s.start()
    s.join(0.5)
    assert s.is_alive(), "save must wait for the writer holding the clock"
    release_writer.set()
    w.join(5)
    s.join(5)
    assert outcome == [SaveOutcome.REQUEUED]


def _expected(tenant_id: int, derivation: str, key: str):
    ctx = Context(tenant_id, reads.committed_version(tenant_id))
    return registry.get(derivation).fn(ctx, key)


def test_no_lost_invalidation_under_concurrent_writes_and_workers(tenant):
    """Writers backdate salaries while workers recompute. Once both stop and
    the queue drains, every result must match a from-scratch computation."""
    employees = [str(i) for i in range(4)]
    months = [f"2024-{m:02d}" for m in range(1, 7)]
    start = Span(D(2024, 1, 1))
    writes.apply(
        tenant.id,
        [Assert(f"employee:{e}", "annual_salary_cents", start, 36_500_00) for e in employees]
        + [Assert(f"employee:{e}", "fte_bp", start, 10_000) for e in employees],
    )
    keys = [f"{e}:{m}" for e in employees for m in months]
    worker.request(tenant.id, "payroll.gross", keys)

    stop = threading.Event()

    @in_thread
    def writer(seed):
        rng = random.Random(seed)
        for _ in range(25):
            e = rng.choice(employees)
            day = D(2024, rng.randint(1, 6), rng.randint(1, 28))
            attr, value = rng.choice(
                [
                    ("annual_salary_cents", rng.randint(30_000, 90_000) * 100),
                    ("fte_bp", rng.choice([5_000, 8_000, 10_000])),
                ]
            )
            writes.apply(tenant.id, [Assert(f"employee:{e}", attr, Span(day), value)])

    @in_thread
    def work(name):
        while not stop.is_set():
            for c in worker.claim(name, 3, tenant.id):
                worker.run_one(c)

    workers = [threading.Thread(target=work, args=(f"w{i}",)) for i in range(4)]
    for t in workers:
        t.start()
    with ThreadPoolExecutor(3) as pool:
        list(pool.map(writer, range(3)))
    stop.set()
    for t in workers:
        t.join(30)

    worker.drain("final", tenant_id=tenant.id)
    rows = Computation.objects.filter(tenant=tenant)
    assert all(c.status == "fresh" for c in rows)
    for c in rows:
        assert c.result == _expected(tenant.id, c.derivation, c.key), c.key
        deltas = Restatement.objects.filter(computation=c).values_list("delta", flat=True)
        assert sum(d.get("gross_cents", 0) for d in deltas) == c.result["gross_cents"]


def test_workers_never_compute_the_same_row_at_once(tenant):
    writes.apply(
        tenant.id,
        [
            Assert("employee:1", "annual_salary_cents", Span(D(2024, 1, 1)), 36_500_00),
            Assert("employee:1", "fte_bp", Span(D(2024, 1, 1)), 10_000),
        ],
    )
    keys = [f"1:{y}-{m:02d}" for y in (2024, 2025) for m in range(1, 13)]
    worker.request(tenant.id, "payroll.gross", keys)
    seen: list[int] = []
    lock = threading.Lock()

    @in_thread
    def work(name):
        while claims := worker.claim(name, 2, tenant.id):
            with lock:
                seen.extend(c.computation_id for c in claims)
            for c in claims:
                worker.run_one(c)

    with ThreadPoolExecutor(6) as pool:
        list(pool.map(work, [f"w{i}" for i in range(6)]))
    assert len(seen) == len(set(seen)) == len(keys)
    assert Restatement.objects.filter(computation__tenant=tenant).count() == len(keys)
