"""HTTP API, version 1.

Every handler runs as one tenant, taken from the API key. Nothing in a URL
or body can name another tenant.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import date
from functools import wraps
from typing import Any

from django.core.exceptions import RequestDataTooBig
from django.db import connection
from django.db.models import Count
from django.http import HttpRequest, JsonResponse

from backdate import conf, reads, writes
from backdate.api.errors import (
    BadRequest,
    Conflict,
    Forbidden,
    NotFound,
    Overloaded,
    PayloadTooLarge,
)
from backdate.api.keys import Principal
from backdate.derive import registry, worker
from backdate.intervals import Span, SpanError, parse_span
from backdate.models import ChangeRange, Changeset, Computation, DerivedRead, ReadRange
from backdate.observability import metrics

View = Callable[..., JsonResponse]


def endpoint(scope: str, methods: tuple[str, ...] = ("GET",)) -> Callable[[View], View]:
    def wrap(fn: View) -> View:
        @wraps(fn)
        def handler(request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
            if request.method not in methods:
                resp = JsonResponse(
                    {"error": {"code": "method_not_allowed", "message": request.method}},
                    status=405,
                )
                resp["Allow"] = ", ".join(methods)
                return resp
            principal: Principal = request.principal  # type: ignore[attr-defined]
            if scope not in principal.scopes:
                raise Forbidden(f"this key lacks the {scope!r} scope")
            return fn(request, principal.tenant_id, *args, **kwargs)

        return handler

    return wrap


# ---- parsing helpers -------------------------------------------------------


def _body(request: HttpRequest) -> tuple[Any, bytes]:
    try:
        raw = request.body
    except RequestDataTooBig:
        raise PayloadTooLarge("request body too large") from None
    try:
        return json.loads(raw or b"null"), raw
    except json.JSONDecodeError as exc:
        raise BadRequest(f"invalid JSON: {exc.msg}") from None


def _int(
    request: HttpRequest,
    name: str,
    default: int | None = None,
    *,
    lo: int = 0,
    hi: int | None = None,
) -> int | None:
    raw = request.GET.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise BadRequest(f"{name} must be an integer") from None
    if value < lo or (hi is not None and value > hi):
        raise BadRequest(f"{name} out of range")
    return value


def _date(raw: str | None, name: str) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise BadRequest(f"{name} must be YYYY-MM-DD") from None


def _span_json(span: Span) -> dict[str, str | None]:
    return {"from": span.start.isoformat(), "to": span.end.isoformat() if span.end else None}


def _version(request: HttpRequest, tenant_id: int) -> int:
    latest = reads.committed_version(tenant_id)
    asked = _int(request, "version")
    if asked is None:
        return latest
    if asked > latest:
        raise BadRequest(f"version {asked} is in the future, latest is {latest}")
    return asked


# ---- writes ----------------------------------------------------------------


def _parse_ops(body: Any) -> list[writes.Op]:
    if not isinstance(body, dict) or not isinstance(body.get("ops"), list):
        raise BadRequest('body must be an object with an "ops" list')
    ops: list[writes.Op] = []
    for i, raw in enumerate(body["ops"]):
        if not isinstance(raw, dict):
            raise BadRequest(f"ops[{i}] must be an object")
        kind = raw.get("op")
        entity, attribute = raw.get("entity"), raw.get("attribute")
        if not isinstance(entity, str) or not isinstance(attribute, str):
            raise BadRequest(f"ops[{i}] needs string entity and attribute")
        start, end = raw.get("from"), raw.get("to")
        if not isinstance(start, str) or not (end is None or isinstance(end, str)):
            raise BadRequest(f'ops[{i}] needs "from" (YYYY-MM-DD) and optional "to"')
        try:
            span = parse_span(start, end)
        except SpanError as exc:
            raise BadRequest(f"ops[{i}]: {exc}") from None
        if kind == "assert":
            if "value" not in raw or raw["value"] is None:
                raise BadRequest(f"ops[{i}]: assert needs a non-null value; use retract instead")
            ops.append(writes.Assert(entity, attribute, span, raw["value"]))
        elif kind == "retract":
            ops.append(writes.Retract(entity, attribute, span))
        else:
            raise BadRequest(f'ops[{i}].op must be "assert" or "retract"')
    return ops


def _check_backlog(tenant_id: int) -> None:
    limit = conf.get_int("MAX_STALE_BACKLOG")
    if not limit:
        return
    waiting = Computation.objects.filter(
        tenant_id=tenant_id, status__in=[Computation.Status.PENDING, Computation.Status.STALE]
    )[: limit + 1].count()
    if waiting > limit:
        raise Overloaded(
            f"{waiting - 1}+ results are waiting to be recomputed; retry later",
            headers={"Retry-After": "5"},
        )


@endpoint("write", ("POST",))
def write(request: HttpRequest, tenant_id: int) -> JsonResponse:
    body, raw = _body(request)
    ops = _parse_ops(body)
    key = request.headers.get("Idempotency-Key")
    if key is not None and not (0 < len(key) <= 200):
        raise BadRequest("Idempotency-Key must be 1-200 characters")
    dry_run = body.get("dry_run", False)
    if not isinstance(dry_run, bool):
        raise BadRequest("dry_run must be true or false")
    reason = body.get("reason", "")
    if not isinstance(reason, str) or len(reason) > 2000:
        raise BadRequest("reason must be a string of at most 2000 characters")
    if dry_run:
        try:
            result = writes.apply(tenant_id, ops, reason=reason, dry_run=True)
        except writes.WriteError as exc:
            raise BadRequest(str(exc)) from None
        metrics.writes.labels("dry_run").inc()
        return JsonResponse(result.as_json())
    _check_backlog(tenant_id)
    with metrics.write_seconds.time():
        try:
            result = writes.apply(
                tenant_id,
                ops,
                actor=f"key:{request.principal.key_id}",  # type: ignore[attr-defined]
                reason=reason,
                idempotency_key=key,
                request_hash=hashlib.sha256(raw).hexdigest(),
            )
        except writes.IdempotencyConflict as exc:
            metrics.writes.labels("conflict").inc()
            raise Conflict(str(exc)) from None
        except writes.WriteError as exc:
            metrics.writes.labels("rejected").inc()
            raise BadRequest(str(exc)) from None
    outcome = "replayed" if result.replayed else "noop" if result.noop else "applied"
    metrics.writes.labels(outcome).inc()
    metrics.invalidated.inc(0 if result.replayed else result.invalidated)
    resp = JsonResponse(result.as_json())
    if result.replayed:
        resp["Idempotent-Replayed"] = "true"
    return resp


# ---- fact reads ------------------------------------------------------------


@endpoint("read")
def timeline(request: HttpRequest, tenant_id: int, entity: str, attribute: str) -> JsonResponse:
    version = _version(request, tenant_id)
    start = _date(request.GET.get("from"), "from")
    end = _date(request.GET.get("to"), "to")
    within = None
    if start or end:
        try:
            within = Span(start or date.min, end)
        except SpanError as exc:
            raise BadRequest(str(exc)) from None
    pieces = reads.timeline(tenant_id, entity, attribute, within=within, version=version)
    return JsonResponse(
        {
            "entity": entity,
            "attribute": attribute,
            "version": version,
            "pieces": [{**_span_json(p.span), "value": p.value} for p in pieces],
        }
    )


@endpoint("read")
def history(request: HttpRequest, tenant_id: int, entity: str, attribute: str) -> JsonResponse:
    rows = reads.history(tenant_id, entity, attribute)
    return JsonResponse(
        {
            "entity": entity,
            "attribute": attribute,
            "rows": [
                {**_span_json(r.span), "value": r.value, "tx_from": r.tx_from, "tx_to": r.tx_to}
                for r in rows
            ],
        }
    )


@endpoint("read")
def entity(request: HttpRequest, tenant_id: int, entity: str) -> JsonResponse:
    version = _version(request, tenant_id)
    on = _date(request.GET.get("on"), "on")
    if on is None:
        raise BadRequest("on=YYYY-MM-DD is required")
    return JsonResponse(
        {
            "entity": entity,
            "on": on.isoformat(),
            "version": version,
            "attributes": reads.entity_at(tenant_id, entity, on, version=version),
        }
    )


@endpoint("read")
def changesets(request: HttpRequest, tenant_id: int) -> JsonResponse:
    after = _int(request, "after_version", 0)
    limit = _int(request, "limit", 50, lo=1, hi=500)
    rows = list(
        Changeset.objects.filter(tenant_id=tenant_id, version__gt=after)
        .order_by("version")[:limit]
        .values("id", "version", "recorded_at", "actor", "reason")
    )
    ranges: dict[int, list[dict[str, Any]]] = {}
    for r in ChangeRange.objects.filter(changeset_id__in=[c["id"] for c in rows]).values(
        "changeset_id", "entity", "attribute", "valid"
    ):
        ranges.setdefault(r["changeset_id"], []).append(
            {
                "entity": r["entity"],
                "attribute": r["attribute"],
                **_span_json(Span.from_range(r["valid"])),
            }
        )
    return JsonResponse(
        {
            "changesets": [
                {
                    "version": c["version"],
                    "recorded_at": c["recorded_at"].isoformat(),
                    "actor": c["actor"],
                    "reason": c["reason"],
                    "changes": ranges.get(c["id"], []),
                }
                for c in rows
            ]
        }
    )


@endpoint("read")
def clock(request: HttpRequest, tenant_id: int) -> JsonResponse:
    counts = dict(
        Computation.objects.filter(tenant_id=tenant_id)
        .values("status")
        .annotate(n=Count("id"))
        .values_list("status", "n")
    )
    return JsonResponse(
        {
            "version": reads.committed_version(tenant_id),
            "computations": {s: counts.get(s, 0) for s in Computation.Status.values},
        }
    )


# ---- computations ----------------------------------------------------------


@endpoint("read")
def derivations(request: HttpRequest, tenant_id: int) -> JsonResponse:
    return JsonResponse(
        {
            "derivations": [
                {"name": d.name, "version": d.version, "description": d.description}
                for d in registry.all_derivations()
            ]
        }
    )


def _computation_json(c: Computation) -> dict[str, Any]:
    return {
        "id": c.id,
        "derivation": c.derivation,
        "key": c.key,
        "status": c.status,
        "result": c.result,
        "result_version": c.result_version,
        "result_seq": c.result_seq,
        "stale_since_version": c.stale_since_version,
        "attempts": c.attempts,
        "last_error": c.last_error,
        "lease": {
            "owner": c.lease_owner,
            "token": c.lease_token,
            "expires_at": c.lease_expires_at.isoformat() if c.lease_expires_at else None,
        },
        "updated_at": c.updated_at.isoformat(),
    }


@endpoint("read", ("GET", "POST"))
def computations(request: HttpRequest, tenant_id: int) -> JsonResponse:
    if request.method == "POST":
        return _request_computations(request, tenant_id)
    qs = Computation.objects.filter(tenant_id=tenant_id)
    if derivation := request.GET.get("derivation"):
        qs = qs.filter(derivation=derivation)
    if status := request.GET.get("status"):
        if status not in Computation.Status.values:
            raise BadRequest(f"status must be one of {Computation.Status.values}")
        qs = qs.filter(status=status)
    if prefix := request.GET.get("key_prefix"):
        qs = qs.filter(key__startswith=prefix)
    after = _int(request, "after_id", 0)
    limit = _int(request, "limit", 100, lo=1, hi=1000)
    rows = list(qs.filter(id__gt=after).order_by("id")[:limit])
    return JsonResponse(
        {
            "computations": [_computation_json(c) for c in rows],
            "next_after_id": rows[-1].id if len(rows) == limit else None,
        }
    )


def _request_computations(request: HttpRequest, tenant_id: int) -> JsonResponse:
    if "compute" not in request.principal.scopes:  # type: ignore[attr-defined]
        raise Forbidden("this key lacks the 'compute' scope")
    body, _ = _body(request)
    if not isinstance(body, dict):
        raise BadRequest("body must be an object")
    name, keys = body.get("derivation"), body.get("keys")
    if not isinstance(name, str) or not isinstance(keys, list):
        raise BadRequest('body needs "derivation" and a "keys" list')
    if not all(isinstance(k, str) and 0 < len(k) <= 300 for k in keys) or len(keys) > 5000:
        raise BadRequest("keys must be 1-300 character strings, at most 5000 of them")
    try:
        created = worker.request(tenant_id, name, keys)
    except registry.UnknownDerivation:
        raise NotFound(f"no derivation named {name!r}") from None
    return JsonResponse({"requested": len(set(keys)), "created": created}, status=202)


@endpoint("read")
def computation(request: HttpRequest, tenant_id: int, computation_id: int) -> JsonResponse:
    c = Computation.objects.filter(tenant_id=tenant_id, id=computation_id).first()
    if c is None:
        raise NotFound("no such computation")
    body = _computation_json(c)
    body["reads"] = [
        {"entity": r.entity, "attribute": r.attribute, **_span_json(Span.from_range(r.valid))}
        for r in ReadRange.objects.filter(computation=c).order_by("entity", "attribute", "valid")
    ]
    body["depends_on"] = [
        {"id": d.source_id, "observed_seq": d.observed_seq}
        for d in DerivedRead.objects.filter(reader=c)
    ]
    body["dependents"] = list(
        DerivedRead.objects.filter(source=c).values_list("reader_id", flat=True)
    )
    body["restatements"] = [_restatement_json(r) for r in c.restatements.order_by("seq")]
    return JsonResponse(body)


# ---- restatement feed ------------------------------------------------------

_FEED_SQL = """
SELECT r.id, r.txid, r.seq, r.from_version, r.to_version, r.previous, r.current, r.delta,
       r.created_at, c.id, c.derivation, c.key
  FROM backdate_restatement r
  JOIN backdate_computation c ON c.id = r.computation_id
 WHERE r.tenant_id = %s
   AND (r.txid, r.id) > (%s, %s)
   -- Only rows from transactions older than every one still running. A row
   -- with a smaller txid can then never appear later, so the cursor is safe.
   AND r.txid < pg_snapshot_xmin(pg_current_snapshot())::text::bigint
 ORDER BY r.txid, r.id
 LIMIT %s
"""


def _restatement_json(r: Any) -> dict[str, Any]:
    return {
        "seq": r.seq,
        "from_version": r.from_version,
        "to_version": r.to_version,
        "previous": r.previous,
        "current": r.current,
        "delta": r.delta,
        "created_at": r.created_at.isoformat(),
    }


def _parse_cursor(raw: str | None) -> tuple[int, int]:
    if not raw:
        return 0, 0
    try:
        txid, rid = raw.split(".")
        return int(txid), int(rid)
    except ValueError:
        raise BadRequest("cursor is malformed") from None


@endpoint("read")
def feed(request: HttpRequest, tenant_id: int) -> JsonResponse:
    txid, rid = _parse_cursor(request.GET.get("cursor"))
    limit = _int(request, "limit", 100, lo=1, hi=1000)
    with connection.cursor() as cur:
        cur.execute(_FEED_SQL, [tenant_id, txid, rid, limit])
        rows = cur.fetchall()
    items = [
        {
            "computation": {"id": row[9], "derivation": row[10], "key": row[11]},
            "seq": row[2],
            "from_version": row[3],
            "to_version": row[4],
            "previous": _json(row[5]),
            "current": _json(row[6]),
            "delta": _json(row[7]),
            "created_at": row[8].isoformat(),
        }
        for row in rows
    ]
    cursor = f"{rows[-1][1]}.{rows[-1][0]}" if rows else (request.GET.get("cursor") or "0.0")
    return JsonResponse({"restatements": items, "cursor": cursor})


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


# ---- dependency graph ------------------------------------------------------


@endpoint("read")
def graph(request: HttpRequest, tenant_id: int) -> JsonResponse:
    """Computations with their read sets and derived edges, in one response.

    Meant for visualising which facts feed which results. Filter by
    ``key_prefix`` to keep it small; ``limit`` caps the computation count.
    """
    limit = _int(request, "limit", 200, lo=1, hi=2000) or 200
    qs = Computation.objects.filter(tenant_id=tenant_id).order_by("id")
    if prefix := request.GET.get("key_prefix"):
        qs = qs.filter(key__startswith=prefix)
    comps = list(qs[:limit])
    ids = [c.id for c in comps]
    reads_by: dict[int, list[dict[str, Any]]] = {}
    for r in ReadRange.objects.filter(computation_id__in=ids).values(
        "computation_id", "entity", "attribute", "valid"
    ):
        reads_by.setdefault(r["computation_id"], []).append(
            {
                "entity": r["entity"],
                "attribute": r["attribute"],
                **_span_json(Span.from_range(r["valid"])),
            }
        )
    edges = [
        {"source": s, "reader": rd, "observed_seq": seq}
        for s, rd, seq in DerivedRead.objects.filter(reader_id__in=ids).values_list(
            "source_id", "reader_id", "observed_seq"
        )
    ]
    return JsonResponse(
        {
            "version": reads.committed_version(tenant_id),
            "computations": [
                {**_computation_json(c), "reads": reads_by.get(c.id, [])} for c in comps
            ],
            "edges": edges,
            "truncated": len(comps) == limit,
        }
    )
