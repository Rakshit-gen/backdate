"""Benchmark harness.

    uv run python bench/run.py                # default sizes, a few minutes
    uv run python bench/run.py --employees 50 # quick smoke run

Uses its own database (``backdate_bench`` unless PGDATABASE is set), drops
and recreates it on every run, and writes raw numbers to
``bench/results/<timestamp>.json`` plus a markdown table on stdout.

Scenarios:

1. write_latency       single backdated raises against a fully computed tenant
2. initial_compute     drain the whole queue with 1, 2 and 4 worker processes
3. backdate_targeted   one raise, time until every result is fresh again
4. backdate_naive      same raise, but every result is marked stale, which is
                       what you do without read sets
5. clock_contention    concurrent writers in one tenant vs spread over tenants
6. lease_recovery      SIGKILL a worker mid-compute, time until its work lands
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import signal
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "server.settings")
os.environ.setdefault("PGDATABASE", "backdate_bench")
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("BACKDATE_MAX_STALE_BACKLOG", "0")

import django  # noqa: E402

django.setup()

from django.core.management import call_command  # noqa: E402
from django.db import connection, connections  # noqa: E402

from backdate import writes  # noqa: E402
from backdate.derive import worker  # noqa: E402
from backdate.intervals import Span  # noqa: E402
from backdate.models import Computation, Tenant, TenantClock  # noqa: E402
from backdate.writes import Assert  # noqa: E402
from examples.payroll.seed import Plan, seed  # noqa: E402

DB = os.environ["PGDATABASE"]


def pct(samples: list[float], p: float) -> float:
    ordered = sorted(samples)
    k = max(0, min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1))))
    return ordered[k]


def summary(samples_ms: list[float]) -> dict[str, float]:
    return {
        "n": len(samples_ms),
        "p50_ms": round(pct(samples_ms, 50), 2),
        "p95_ms": round(pct(samples_ms, 95), 2),
        "p99_ms": round(pct(samples_ms, 99), 2),
        "mean_ms": round(statistics.fmean(samples_ms), 2),
    }


def reset_db() -> None:
    connections.close_all()
    admin = dict(connection.settings_dict)
    env = {**os.environ, "PGDATABASE": "postgres"}
    port = str(admin["PORT"])
    for sql in (f"DROP DATABASE IF EXISTS {DB} WITH (FORCE)", f"CREATE DATABASE {DB}"):
        subprocess.run(  # noqa: S603
            ["psql", "-p", port, "-h", admin["HOST"], "-qc", sql],  # noqa: S607
            check=True,
            env=env,
        )
    call_command("migrate", verbosity=0)


def make_tenant(slug: str) -> Tenant:
    t = Tenant.objects.create(slug=slug, name=slug)
    TenantClock.objects.create(tenant=t)
    return t


def drain_with_processes(n: int) -> float:
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    started = time.perf_counter()
    procs = [
        subprocess.Popen(  # noqa: S603
            [
                sys.executable,
                "manage.py",
                "backdate_worker",
                "--once",
                "--batch",
                "20",
                "--name",
                f"bench{i}",
            ],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
        )
        for i in range(n)
    ]
    for p in procs:
        p.wait()
    return time.perf_counter() - started


def requeue_all(tenant: Tenant) -> int:
    return Computation.objects.filter(tenant=tenant).update(
        status="stale", attempts=0, not_before=None
    )


def scenario_initial_compute(employees: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for procs in (1, 2, 4):
        reset_db()
        t = make_tenant("init")
        keys = seed(t.id, Plan(employees))
        total = len(keys) * 2
        seconds = drain_with_processes(procs)
        fresh = Computation.objects.filter(tenant=t, status="fresh").count()
        assert fresh == total, (fresh, total)
        out[f"{procs}_proc"] = {
            "results": total,
            "seconds": round(seconds, 2),
            "results_per_sec": round(total / seconds, 1),
        }
    return out


def raise_op(emp: int, month: int, cents: int) -> Assert:
    return Assert(f"employee:{emp}", "annual_salary_cents", Span(date(2024, month, 1)), cents)


def scenario_write_latency(tenant: Tenant, employees: int, n: int) -> dict[str, Any]:
    samples = []
    invalidated = []
    for i in range(n):
        emp = 1 + i % employees
        op = raise_op(emp, 1 + i % 12, 50_000_00 + i * 100)
        started = time.perf_counter()
        r = writes.apply(tenant.id, [op])
        samples.append((time.perf_counter() - started) * 1000)
        invalidated.append(r.invalidated)
    worker.drain("bench-latency", tenant_id=tenant.id)
    return {**summary(samples), "mean_invalidated": round(statistics.fmean(invalidated), 2)}


def time_to_fresh(tenant: Tenant, procs: int) -> float:
    return drain_with_processes(procs)


def scenario_backdate(tenant: Tenant, procs: int) -> dict[str, Any]:
    # A raise effective 1 July for one employee touches 6 gross + 6 withholding.
    started = time.perf_counter()
    r = writes.apply(tenant.id, [raise_op(1, 7, 99_000_00)])
    write_ms = (time.perf_counter() - started) * 1000
    drain_s = time_to_fresh(tenant, procs)
    targeted = {
        "invalidated": r.invalidated,
        "write_ms": round(write_ms, 2),
        "seconds_to_consistent": round(write_ms / 1000 + drain_s, 3),
    }
    # Baseline: no read sets, so any change means everything is suspect.
    started = time.perf_counter()
    writes.apply(tenant.id, [raise_op(2, 7, 98_000_00)])
    n = requeue_all(tenant)
    mark_s = time.perf_counter() - started
    drain_s = time_to_fresh(tenant, procs)
    naive = {"invalidated": n, "seconds_to_consistent": round(mark_s + drain_s, 3)}
    return {"targeted": targeted, "naive_recompute_all": naive, "worker_processes": procs}


def scenario_clock_contention(writers: int, per_writer: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for mode in ("one_tenant", "tenant_per_writer"):
        tenants = [make_tenant(f"{mode}{i}") for i in range(writers if mode != "one_tenant" else 1)]

        def run(i: int, tenants: list[Tenant] = tenants) -> list[float]:
            t = tenants[i % len(tenants)]
            samples = []
            try:
                for j in range(per_writer):
                    op = Assert(f"e{i}", "a", Span(date(2024, 1, 1 + j % 28)), j)
                    s = time.perf_counter()
                    writes.apply(t.id, [op])
                    samples.append((time.perf_counter() - s) * 1000)
            finally:
                connections.close_all()
            return samples

        started = time.perf_counter()
        with ThreadPoolExecutor(writers) as pool:
            all_samples = [x for chunk in pool.map(run, range(writers)) for x in chunk]
        seconds = time.perf_counter() - started
        out[mode] = {
            **summary(all_samples),
            "writes_per_sec": round(len(all_samples) / seconds, 1),
            "writers": writers,
        }
    return out


def scenario_lease_recovery(lease_seconds: int) -> dict[str, Any]:
    reset_db()
    t = make_tenant("lease")
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "BACKDATE_LEASE_SECONDS": str(lease_seconds),
        "BACKDATE_DERIVATION_MODULES": "examples.payroll.derivations,tests.slow_derivations",
    }
    writes.apply(t.id, [Assert("job", "sleep_ms", Span(date(2024, 1, 1)), 600_000)])
    os.environ["BACKDATE_DERIVATION_MODULES"] = env["BACKDATE_DERIVATION_MODULES"]
    import tests.slow_derivations  # noqa: F401, PLC0415

    worker.request(t.id, "test.slow", ["job"])
    victim = subprocess.Popen(
        [sys.executable, "manage.py", "backdate_worker", "--batch", "1", "--name", "victim"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
    )
    while not Computation.objects.filter(key="job", lease_owner="victim").exists():
        time.sleep(0.02)
    victim.send_signal(signal.SIGKILL)
    victim.wait()
    killed_at = time.perf_counter()
    writes.apply(t.id, [Assert("job", "sleep_ms", Span(date(2024, 1, 1)), 0)])
    while True:
        claims = worker.claim("rescuer", 1, t.id)
        if claims:
            worker.run_one(claims[0])
            break
        time.sleep(0.05)
    recovered = time.perf_counter() - killed_at
    return {"lease_seconds": lease_seconds, "seconds_until_redone": round(recovered, 2)}


def machine() -> dict[str, Any]:
    with connection.cursor() as cur:
        cur.execute("SHOW server_version")
        pg = cur.fetchone()[0]  # type: ignore[index]
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "cpu_count": os.cpu_count(),
        "postgres": pg,
        "postgres_host": connection.settings_dict["HOST"],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--employees", type=int, default=200)
    ap.add_argument("--writes", type=int, default=300)
    ap.add_argument("--writers", type=int, default=8)
    ap.add_argument("--per-writer", type=int, default=50)
    ap.add_argument("--lease-seconds", type=int, default=3)
    args = ap.parse_args()

    results: dict[str, Any] = {"started_at": datetime.now(UTC).isoformat(), "args": vars(args)}
    print(f"initial compute, {args.employees} employees x 12 months x 2 derivations", flush=True)
    results["initial_compute"] = scenario_initial_compute(args.employees)
    results["machine"] = machine()

    # The last initial_compute run leaves a fully computed tenant behind.
    tenant = Tenant.objects.get(slug="init")
    print("write latency", flush=True)
    results["write_latency"] = scenario_write_latency(tenant, args.employees, args.writes)
    print("backdate: targeted vs naive", flush=True)
    results["backdate"] = scenario_backdate(tenant, 4)
    print("clock contention", flush=True)
    results["clock_contention"] = scenario_clock_contention(args.writers, args.per_writer)
    print("lease recovery", flush=True)
    results["lease_recovery"] = scenario_lease_recovery(args.lease_seconds)

    out_dir = ROOT / "bench" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"{stamp}.json"
    path.write_text(json.dumps(results, indent=2))
    print(json.dumps(results, indent=2))
    print(f"\nwrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
