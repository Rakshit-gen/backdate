"""Kill things and check nothing is lost or half-written."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from datetime import date
from pathlib import Path

import pytest
from django.db import OperationalError, connection, connections, transaction

import tests.slow_derivations  # noqa: F401 - registers test.slow in this process
from backdate import clock, reads, writes
from backdate.derive import registry, worker
from backdate.derive.context import Context
from backdate.derive.save import save
from backdate.intervals import Span
from backdate.models import Computation, Fact, Restatement
from backdate.writes import Assert

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.slow]
ROOT = Path(__file__).resolve().parent.parent
JAN = Span(date(2024, 1, 1))


def start_worker(lease_seconds: int) -> subprocess.Popen[bytes]:
    env = {
        **os.environ,
        "PGDATABASE": connection.settings_dict["NAME"],
        "BACKDATE_LEASE_SECONDS": str(lease_seconds),
        "BACKDATE_DERIVATION_MODULES": "examples.payroll.derivations,tests.slow_derivations",
        "PYTHONPATH": str(ROOT),
    }
    return subprocess.Popen(
        [
            sys.executable,
            "manage.py",
            "backdate_worker",
            "--batch",
            "1",
            "--idle-sleep",
            "0.05",
            "--name",
            "victim",
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def wait_for(predicate, timeout=15.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def test_sigkilled_worker_lease_expires_and_work_is_redone(tenant):
    writes.apply(
        tenant.id, [Assert("job", "sleep_ms", JAN, 60_000), Assert("job", "value", JAN, 1)]
    )
    worker.request(tenant.id, "test.slow", ["job"])
    proc = start_worker(lease_seconds=2)
    try:
        assert wait_for(lambda: Computation.objects.filter(lease_owner="victim").exists()), (
            proc.stdout.read1().decode() if proc.stdout else ""
        )
        proc.send_signal(signal.SIGKILL)
        proc.wait(5)
    finally:
        if proc.poll() is None:
            proc.kill()

    c = Computation.objects.get(key="job")
    assert c.status == "pending"
    assert c.lease_owner == "victim"
    assert worker.claim("me", tenant_id=tenant.id) == [], "lease is still live"

    writes.apply(tenant.id, [Assert("job", "sleep_ms", JAN, 0)])
    claims: list[worker.Claim] = []
    assert wait_for(lambda: bool(claims.extend(worker.claim("me", tenant_id=tenant.id)) or claims))
    assert claims[0].token == 2
    assert worker.run_one(claims[0]).outcome == "saved"
    c.refresh_from_db()
    assert c.status == "fresh"
    assert Restatement.objects.filter(computation=c).count() == 1


def test_sigterm_finishes_cleanly(tenant):
    proc = start_worker(lease_seconds=5)
    time.sleep(1.5)
    proc.send_signal(signal.SIGTERM)
    assert proc.wait(10) == 0
    out = proc.stdout.read().decode() if proc.stdout else ""
    assert "stopped" in out


def _terminate(pid: int) -> None:
    other = connections.create_connection("default")
    try:
        with other.cursor() as cur:
            cur.execute("SELECT pg_terminate_backend(%s)", [pid])
    finally:
        other.close()


def test_writer_killed_mid_transaction_leaves_no_trace(tenant):
    writes.apply(tenant.id, [Assert("e", "a", JAN, 1)])
    ready = threading.Event()
    pid: list[int] = []
    errors: list[Exception] = []

    def doomed():
        try:
            with transaction.atomic():
                clock.lock_for_write(tenant.id)
                with connection.cursor() as cur:
                    cur.execute("SELECT pg_backend_pid()")
                    pid.append(cur.fetchone()[0])
                ready.set()
                with connection.cursor() as cur:
                    cur.execute("SELECT pg_sleep(10)")
        except OperationalError as exc:
            errors.append(exc)
        finally:
            connections.close_all()

    t = threading.Thread(target=doomed)
    t.start()
    assert ready.wait(5)
    _terminate(pid[0])
    t.join(10)
    assert errors, "the killed transaction should have failed"

    assert reads.committed_version(tenant.id) == 1
    result = writes.apply(tenant.id, [Assert("e", "a", JAN, 2)])
    assert result.version == 2
    assert Fact.objects.filter(tenant=tenant, tx_to__isnull=True).count() == 1


def test_connection_lost_during_save_leaves_row_claimable(tenant, settings):
    writes.apply(tenant.id, [Assert("job", "value", JAN, 5)])
    worker.request(tenant.id, "test.slow", ["job"])
    (claim,) = worker.claim("w", tenant_id=tenant.id)
    ctx = Context(tenant.id, reads.committed_version(tenant.id))
    result = registry.get("test.slow").fn(ctx, "job")

    with connection.cursor() as cur:
        cur.execute("SELECT pg_backend_pid()")
        my_pid = cur.fetchone()[0]
    _terminate(my_pid)
    with pytest.raises(OperationalError):
        save(claim, ctx, result, "1")
    connection.close()

    c = Computation.objects.get(key="job")
    assert c.result is None
    assert not Restatement.objects.filter(computation=c).exists()
    Computation.objects.filter(id=c.id).update(lease_expires_at=None)
    worker.drain("w2", tenant_id=tenant.id)
    c.refresh_from_db()
    assert c.status == "fresh"
    assert c.result == {"value": 5}
