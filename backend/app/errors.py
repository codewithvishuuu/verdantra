"""Standard API error envelope (API.md section 6) + request-ID plumbing.

Every 4xx/5xx looks like:
  {"error": {"code": ..., "message": ..., "details": {...}}, "request_id": ...}
`details` carries only safe context (e.g. model_id, temp_image_id).
Never traces, paths, provider bodies, image bytes, or secrets.
"""

import secrets
from typing import Any, Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str,
                 details: Optional[dict] = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}


def new_request_id() -> str:
    return "req_" + secrets.token_hex(8)


def envelope(request_id: str, code: str, message: str, details: dict) -> dict:
    return {"error": {"code": code, "message": message, "details": details},
            "request_id": request_id}


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Assigns X-Request-Id to every request/response (frontend shows it on errors)."""

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        request_id = request.headers.get("X-Request-Id") or new_request_id()
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-Id"] = request_id
        return response


def request_id_of(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    body = envelope(request_id_of(request), exc.code, exc.message, exc.details)
    return JSONResponse(status_code=exc.status, content=body,
                        headers={"X-Request-Id": request_id_of(request)})


async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    # Deliberately generic: no traceback, no paths, no internals leak.
    body = envelope(request_id_of(request), "internal_error",
                    "Something went wrong. Please retry.", {})
    return JSONResponse(status_code=500, content=body,
                        headers={"X-Request-Id": request_id_of(request)})


async def not_found_handler(request: Request, exc: Exception) -> JSONResponse:
    body = envelope(request_id_of(request), "not_found",
                    "That path does not exist.", {})
    return JSONResponse(status_code=404, content=body,
                        headers={"X-Request-Id": request_id_of(request)})
