"""Liveness and readiness.

Liveness says the process can serve a request at all, so it never touches
the database. Readiness checks the database answers and that no migration
is waiting, which is what a load balancer should gate traffic on.
"""

from __future__ import annotations

from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.executor import MigrationExecutor
from django.http import HttpRequest, JsonResponse


def live(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


def ready(request: HttpRequest) -> JsonResponse:
    problems: list[str] = []
    connection = connections[DEFAULT_DB_ALIAS]
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if plan:
            problems.append(f"{len(plan)} unapplied migrations")
    except Exception as exc:  # noqa: BLE001 - any failure means not ready
        problems.append(f"database: {type(exc).__name__}")
    if problems:
        return JsonResponse({"status": "unavailable", "problems": problems}, status=503)
    return JsonResponse({"status": "ok"})
