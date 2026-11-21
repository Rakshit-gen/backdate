from __future__ import annotations

import json

import pytest

from backdate.api import keys
from backdate.derive import worker
from backdate.models import ApiKey
from tests.conftest import Api

pytestmark = pytest.mark.django_db


def hire_body(salary=36_500_00):
    return {
        "reason": "hire",
        "ops": [
            {
                "op": "assert",
                "entity": "employee:1",
                "attribute": "annual_salary_cents",
                "from": "2024-01-01",
                "to": None,
                "value": salary,
            },
            {
                "op": "assert",
                "entity": "employee:1",
                "attribute": "fte_bp",
                "from": "2024-01-01",
                "value": 10_000,
            },
        ],
    }


# ---- auth ------------------------------------------------------------------


def test_missing_token_is_401(client):
    r = client.get("/v1/clock")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"
    assert r["X-Request-Id"]


@pytest.mark.parametrize("token", ["nope", "bk_x", "bk__secret", "bk_abc_wrong", "xx_a_b"])
def test_bad_tokens_are_401(client, tenant, token):
    r = client.get("/v1/clock", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert r.status_code == 401


def test_right_prefix_wrong_secret_is_401(client, tenant):
    _, token = keys.issue(tenant, ["read"])
    tampered = token[:-1] + ("A" if token[-1] != "A" else "B")
    r = client.get("/v1/clock", HTTP_AUTHORIZATION=f"Bearer {tampered}")
    assert r.status_code == 401


def test_revoked_key_is_401(client, tenant):
    key, token = keys.issue(tenant, ["read"])
    ApiKey.objects.filter(id=key.id).update(revoked_at="2024-01-01T00:00:00Z")
    assert client.get("/v1/clock", HTTP_AUTHORIZATION=f"Bearer {token}").status_code == 401


def test_secret_is_not_stored(tenant):
    key, token = keys.issue(tenant, ["read"])
    assert token.split("_", 2)[2] not in key.secret_hash


def test_read_only_key_cannot_write(client, tenant):
    _, token = keys.issue(tenant, ["read"])
    ro = Api(client, token)
    r = ro.post("/v1/writes", hire_body())
    assert r.status_code == 403
    assert (
        ro.post(
            "/v1/computations", {"derivation": "payroll.gross", "keys": ["1:2024-01"]}
        ).status_code
        == 403
    )


def test_unknown_scope_rejected(tenant):
    with pytest.raises(ValueError, match="unknown scopes"):
        keys.issue(tenant, ["admin"])


# ---- writes ----------------------------------------------------------------


def test_write_then_read_timeline(api):
    r = api.post("/v1/writes", hire_body())
    assert r.status_code == 200, r.content
    assert r.json()["version"] == 1
    t = api.get("/v1/facts/employee:1/annual_salary_cents").json()
    assert t["pieces"] == [{"from": "2024-01-01", "to": None, "value": 36_500_00}]


def test_timeline_at_old_version(api):
    api.post("/v1/writes", hire_body())
    api.post("/v1/writes", hire_body(salary=1))
    old = api.get("/v1/facts/employee:1/annual_salary_cents", version=1).json()
    assert old["pieces"][0]["value"] == 36_500_00
    assert api.get("/v1/facts/employee:1/annual_salary_cents", version=99).status_code == 400


def test_timeline_clipped(api):
    api.post("/v1/writes", hire_body())
    t = api.get("/v1/facts/employee:1/fte_bp", **{"from": "2024-03-01", "to": "2024-04-01"})
    assert t.json()["pieces"] == [{"from": "2024-03-01", "to": "2024-04-01", "value": 10_000}]


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {"ops": "x"},
        {"ops": [1]},
        {"ops": [{"op": "upsert", "entity": "e", "attribute": "a", "from": "2024-01-01"}]},
        {"ops": [{"op": "assert", "entity": "e", "attribute": "a", "from": "2024-01-01"}]},
        {
            "ops": [
                {"op": "assert", "entity": "e", "attribute": "a", "from": "01/01/2024", "value": 1}
            ]
        },
        {
            "ops": [
                {
                    "op": "assert",
                    "entity": "e",
                    "attribute": "a",
                    "from": "2024-02-01",
                    "to": "2024-01-01",
                    "value": 1,
                }
            ]
        },
        {
            "ops": [
                {"op": "assert", "entity": 5, "attribute": "a", "from": "2024-01-01", "value": 1}
            ]
        },
        {"ops": []},
    ],
)
def test_bad_write_bodies_are_400(api, body):
    r = api.post("/v1/writes", body)
    assert r.status_code == 400, r.content
    assert r.json()["error"]["code"] == "bad_request"


def test_invalid_json_is_400(api):
    r = api.client.post("/v1/writes", data="{", content_type="application/json", **api.headers)
    assert r.status_code == 400


def test_body_too_large_is_413(api, settings):
    settings.DATA_UPLOAD_MAX_MEMORY_SIZE = 100
    r = api.post("/v1/writes", hire_body())
    assert r.status_code == 413


def test_wrong_method_is_405(api):
    r = api.get("/v1/writes")
    assert r.status_code == 405
    assert r["Allow"] == "POST"


def test_idempotent_write_over_http(api):
    first = api.post("/v1/writes", hire_body(), HTTP_IDEMPOTENCY_KEY="abc")
    second = api.post("/v1/writes", hire_body(), HTTP_IDEMPOTENCY_KEY="abc")
    assert second.json() == first.json()
    assert second["Idempotent-Replayed"] == "true"
    conflict = api.post("/v1/writes", hire_body(salary=5), HTTP_IDEMPOTENCY_KEY="abc")
    assert conflict.status_code == 409


def test_backpressure_returns_503_with_retry_after(api, tenant, settings):
    settings.BACKDATE = {**settings.BACKDATE, "MAX_STALE_BACKLOG": 2}
    api.post("/v1/writes", hire_body())
    worker.request(tenant.id, "payroll.gross", ["1:2024-01", "1:2024-02", "1:2024-03"])
    r = api.post("/v1/writes", hire_body(salary=7))
    assert r.status_code == 503
    assert r["Retry-After"] == "5"
    worker.drain("t", tenant_id=tenant.id)
    assert api.post("/v1/writes", hire_body(salary=7)).status_code == 200


# ---- tenant isolation ------------------------------------------------------


def test_tenant_cannot_read_another_tenants_facts(api, other_api):
    api.post("/v1/writes", hire_body())
    r = other_api.get("/v1/facts/employee:1/annual_salary_cents")
    assert r.json()["pieces"] == []


def test_tenant_cannot_fetch_another_tenants_computation(api, other_api, tenant):
    api.post("/v1/writes", hire_body())
    api.post("/v1/computations", {"derivation": "payroll.gross", "keys": ["1:2024-01"]})
    worker.drain("t", tenant_id=tenant.id)
    cid = api.get("/v1/computations").json()["computations"][0]["id"]
    assert api.get(f"/v1/computations/{cid}").status_code == 200
    assert other_api.get(f"/v1/computations/{cid}").status_code == 404
    assert other_api.get("/v1/computations").json()["computations"] == []
    assert other_api.get("/v1/restatements").json()["restatements"] == []


def test_tenant_versions_are_independent(api, other_api):
    api.post("/v1/writes", hire_body())
    api.post("/v1/writes", hire_body(salary=2))
    assert other_api.post("/v1/writes", hire_body()).json()["version"] == 1


# ---- computations and feed -------------------------------------------------


def test_request_compute_and_inspect(api, tenant):
    api.post("/v1/writes", hire_body())
    r = api.post(
        "/v1/computations", {"derivation": "payroll.gross", "keys": ["1:2024-01", "1:2024-01"]}
    )
    assert r.status_code == 202
    assert r.json() == {"requested": 1, "created": 1}
    worker.drain("t", tenant_id=tenant.id)
    listing = api.get("/v1/computations", status="fresh").json()["computations"]
    detail = api.get(f"/v1/computations/{listing[0]['id']}").json()
    assert detail["result"] == {"gross_cents": 31 * 100_00, "days_paid": 31}
    assert {r["attribute"] for r in detail["reads"]} == {"annual_salary_cents", "fte_bp"}
    assert detail["restatements"][0]["seq"] == 1


def test_unknown_derivation_is_404(api):
    r = api.post("/v1/computations", {"derivation": "nope", "keys": ["a"]})
    assert r.status_code == 404


@pytest.mark.django_db(transaction=True)
def test_feed_pages_with_cursor(api, tenant):
    """Needs real commits: the feed hides rows from transactions still open."""
    api.post("/v1/writes", hire_body())
    months = [f"1:2024-{m:02d}" for m in range(1, 6)]
    api.post("/v1/computations", {"derivation": "payroll.gross", "keys": months})
    worker.drain("t", tenant_id=tenant.id)
    seen = []
    cursor = None
    for _ in range(10):
        params = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        page = api.get("/v1/restatements", **params).json()
        if not page["restatements"]:
            break
        seen.extend(r["computation"]["key"] for r in page["restatements"])
        cursor = page["cursor"]
    assert sorted(seen) == months


def test_feed_hides_rows_from_open_transactions(api, tenant):
    api.post("/v1/writes", hire_body())
    api.post("/v1/computations", {"derivation": "payroll.gross", "keys": ["1:2024-01"]})
    worker.drain("t", tenant_id=tenant.id)
    # The test transaction is still open, so its restatement must stay hidden.
    assert api.get("/v1/restatements").json()["restatements"] == []


def test_feed_rejects_bad_cursor(api):
    assert api.get("/v1/restatements", cursor="zzz").status_code == 400


def test_changesets_and_clock(api):
    api.post("/v1/writes", hire_body())
    cs = api.get("/v1/changesets").json()["changesets"]
    assert cs[0]["version"] == 1
    assert {c["attribute"] for c in cs[0]["changes"]} == {"annual_salary_cents", "fte_bp"}
    assert api.get("/v1/clock").json()["version"] == 1


def test_entity_snapshot(api):
    api.post("/v1/writes", hire_body())
    r = api.get("/v1/entities/employee:1", on="2024-06-01").json()
    assert r["attributes"] == {"annual_salary_cents": 36_500_00, "fte_bp": 10_000}
    assert api.get("/v1/entities/employee:1").status_code == 400


def test_health_endpoints(client, db):
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").status_code == 200


def test_metrics_endpoint(client, db):
    body = client.get("/metrics").content.decode()
    assert "backdate_computations" in body


def test_request_id_is_echoed(client):
    r = client.get("/healthz", HTTP_X_REQUEST_ID="abc-123")
    assert r["X-Request-Id"] == "abc-123"
    r = client.get("/healthz", HTTP_X_REQUEST_ID="bad id with spaces")
    assert r["X-Request-Id"] != "bad id with spaces"


def test_error_bodies_are_json(api):
    r = api.get("/v1/computations/999999")
    assert r.status_code == 404
    assert json.loads(r.content)["error"]["code"] == "not_found"
