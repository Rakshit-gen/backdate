"""Prometheus metrics.

Process-local counters. With several gunicorn workers, run with
``PROMETHEUS_MULTIPROC_DIR`` set so ``/metrics`` aggregates across them.
Backlog gauges are read from the database at scrape time instead, since
they describe shared state.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

writes = Counter("backdate_writes_total", "Write requests by outcome.", ["outcome"])
write_seconds = Histogram(
    "backdate_write_seconds",
    "Time spent in the write transaction.",
    buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5),
)
invalidated = Counter("backdate_invalidated_total", "Results marked stale by writes.")
computations = Counter(
    "backdate_computations_total", "Computation runs by outcome.", ["derivation", "outcome"]
)
compute_seconds = Histogram(
    "backdate_compute_seconds",
    "Time to compute and save one result.",
    ["derivation"],
    buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 10),
)
http_requests = Counter(
    "backdate_http_requests_total", "API requests.", ["route", "method", "status"]
)
