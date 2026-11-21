"""The /metrics endpoint.

Counters come from this process. Backlog gauges are computed per scrape
from the database, since every process sees the same queue.
"""

from __future__ import annotations

import os

from django.db.models import Count
from django.http import HttpRequest, HttpResponse
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, CollectorRegistry, generate_latest
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector

from backdate.models import Computation


class BacklogCollector(Collector):
    def collect(self):  # type: ignore[no-untyped-def]
        gauge = GaugeMetricFamily(
            "backdate_computations", "Computations by status, all tenants.", labels=["status"]
        )
        counts = dict(
            Computation.objects.values("status").annotate(n=Count("id")).values_list("status", "n")
        )
        for status in Computation.Status.values:
            gauge.add_metric([status], counts.get(status, 0))
        yield gauge


_backlog = BacklogCollector()


def metrics_view(request: HttpRequest) -> HttpResponse:
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        from prometheus_client import multiprocess  # noqa: PLC0415

        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)  # type: ignore[no-untyped-call]
    else:
        registry = REGISTRY
    output = generate_latest(registry)
    extra = CollectorRegistry()
    extra.register(_backlog)
    output += generate_latest(extra)
    return HttpResponse(output, content_type=CONTENT_TYPE_LATEST)
