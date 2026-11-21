"""JSON error responses with stable codes.

Clients branch on ``error.code``. The message is for humans and may change.
"""

from __future__ import annotations

from typing import Any

from django.http import JsonResponse


class ApiError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, message: str, *, detail: Any = None, headers: dict[str, str] | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail
        self.headers = headers or {}

    def response(self, request_id: str = "") -> JsonResponse:
        body: dict[str, Any] = {"error": {"code": self.code, "message": self.message}}
        if self.detail is not None:
            body["error"]["detail"] = self.detail
        if request_id:
            body["error"]["request_id"] = request_id
        resp = JsonResponse(body, status=self.status)
        for k, v in self.headers.items():
            resp[k] = v
        return resp


class BadRequest(ApiError):
    pass


class Unauthorized(ApiError):
    status = 401
    code = "unauthorized"


class Forbidden(ApiError):
    status = 403
    code = "forbidden"


class NotFound(ApiError):
    status = 404
    code = "not_found"


class Conflict(ApiError):
    status = 409
    code = "conflict"


class PayloadTooLarge(ApiError):
    status = 413
    code = "payload_too_large"


class Overloaded(ApiError):
    status = 503
    code = "overloaded"
