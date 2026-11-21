"""Request context and API key authentication."""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse
from django.urls import Resolver404, resolve

from backdate import tenancy
from backdate.api import keys
from backdate.api.errors import ApiError, Unauthorized
from backdate.observability import logging as blog
from backdate.observability import metrics

log = logging.getLogger("backdate.http")

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

Handler = Callable[[HttpRequest], HttpResponse]


class RequestContextMiddleware:
    """Request id, access log, metrics, and ApiError to JSON."""

    def __init__(self, get_response: Handler) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming = request.headers.get("X-Request-Id", "")
        request_id = incoming if _REQUEST_ID.match(incoming) else uuid.uuid4().hex
        request.request_id = request_id  # type: ignore[attr-defined]
        blog.clear()
        blog.bind(request_id=request_id)
        started = time.perf_counter()
        response = self.get_response(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response["X-Request-Id"] = request_id
        route = _route(request)
        metrics.http_requests.labels(route, request.method, str(response.status_code)).inc()
        if route not in {"healthz", "readyz", "metrics"}:
            log.info(
                "request",
                extra={
                    "method": request.method,
                    "route": route,
                    "status": response.status_code,
                    "duration_ms": round(elapsed_ms, 2),
                },
            )
        blog.clear()
        return response

    def process_exception(self, request: HttpRequest, exc: Exception) -> HttpResponse | None:
        if isinstance(exc, ApiError):
            return exc.response(getattr(request, "request_id", ""))
        return None


class ApiKeyAuthMiddleware:
    """Resolve ``Authorization: Bearer bk_...`` for paths under /v1/."""

    def __init__(self, get_response: Handler) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if not request.path.startswith("/v1/"):
            return self.get_response(request)
        header = request.headers.get("Authorization", "")
        scheme, _, token = header.partition(" ")
        request_id = getattr(request, "request_id", "")
        if scheme.lower() != "bearer" or not token:
            return Unauthorized("missing bearer token").response(request_id)
        try:
            principal = keys.authenticate(token.strip())
        except keys.InvalidKey as exc:
            return Unauthorized(str(exc)).response(request_id)
        request.principal = principal  # type: ignore[attr-defined]
        blog.bind(tenant_id=principal.tenant_id, key_id=principal.key_id)
        with tenancy.scoped(principal.tenant_id):
            return self.get_response(request)


def _route(request: HttpRequest) -> str:
    # Label metrics by route name, not path, so ids in URLs do not explode
    # the label set.
    try:
        match = resolve(request.path_info)
    except Resolver404:
        return "unmatched"
    return match.url_name or match.route or "unnamed"
