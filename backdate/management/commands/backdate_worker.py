"""Run a recompute worker.

    python manage.py backdate_worker --concurrency 1 --batch 10

Run several of these as separate processes to scale. Each one is single
threaded on purpose: derivations are Python and the GIL would serialize
threads anyway.

SIGTERM and SIGINT finish the current batch and exit. A SIGKILL leaves the
current claims leased; they become claimable again after LEASE_SECONDS.
"""

from __future__ import annotations

import os
import signal
import socket
import time
from types import FrameType
from typing import Any

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from backdate.derive import worker


class Command(BaseCommand):
    help = "Claim and recompute stale or pending results until stopped."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--batch", type=int, default=10)
        parser.add_argument("--idle-sleep", type=float, default=0.5)
        parser.add_argument("--once", action="store_true", help="drain the queue and exit")
        parser.add_argument("--name", default=f"{socket.gethostname()}:{os.getpid()}")
        parser.add_argument(
            "--pace-ms",
            type=int,
            default=0,
            help="sleep this long before each computation, to watch leases in a demo",
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        name: str = opts["name"]
        if opts["once"]:
            done = worker.drain(name, batch=opts["batch"])
            self.stdout.write(f"computed {done}")
            return

        stopping = False

        def stop(signum: int, frame: FrameType | None) -> None:
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        self.stdout.write(f"worker {name} started")
        while not stopping:
            close_old_connections()
            claims = worker.claim(name, opts["batch"])
            if not claims:
                time.sleep(opts["idle_sleep"])
                continue
            for c in claims:
                if opts["pace_ms"]:
                    time.sleep(opts["pace_ms"] / 1000)
                worker.run_one(c)
        self.stdout.write(f"worker {name} stopped")
