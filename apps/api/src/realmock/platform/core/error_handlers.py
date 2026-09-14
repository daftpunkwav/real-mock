"""Unified exception handlers + envelope construction.

Design principles:
- asgi.py/app_factory.py only register routes (@app.exception_handler + handler functions);
  all envelope/spec/headers handling is centralized in this module;
- All 5 handlers share one envelope pipeline as the single source of truth.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from realmock.platform.core.constants import TRACE_ID_HEADER
from realmock.platform.core.errors import CATALOG, ErrorSpec
from realmock.platform.core.logging import get_trace_id
from realmock.platform.core.security import UnsafeURLError

logger = logging.getLogger(__name__)

# ── Envelope Builders ──────────────────────────────────────

def _trace_id() -> str:
    return get_trace_id() or ""


def _envelope(
    *,
    code: str,
    message: str,
    status: int,
    hint: str = "",
    retryable: bool = False,
    extra_headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Construct a unified envelope; automatically write trace_id and extra_headers."""
    resp = JSONResponse(
        status_code=status,
        content={
            "detail": message,
            "error": {
                "code": code,
                "message": message,
                "hint": hint,
                "retryable": retryable,
                "trace_id": _trace_id(),
            },
        },
    )
    tid = get_trace_id()
    if tid:
        resp.headers[TRACE_ID_HEADER] = tid
    for k, v in (extra_headers or {}).items():
        resp.headers[k] = v
    return resp


def _envelope_spec(
    spec: ErrorSpec,
    *,
    message: str | None = None,
    extra_headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build the envelope using all ErrorSpec fields; when message is omitted, use the spec's default message."""
    return _envelope(
        code=spec.code,
        message=message or spec.message,
        status=spec.http_status,
        hint=spec.hint,
        retryable=spec.retryable,
        extra_headers=extra_headers,
    )


# ── HTTPException → envelope unified translator ──

def _detail_str(exc: Exception) -> str:
    """HTTPException.detail may be str or list/dict, which is uniformly converted to str."""
    detail = getattr(exc, "detail", "")
    return detail if isinstance(detail, str) else str(detail)


def _exc_headers(exc: Exception) -> dict[str, str]:
    return dict(getattr(exc, "headers", None) or {})


def _envelope_from_http_exception(exc: HTTPException) -> JSONResponse:
    """Route every HTTPException (shared by FastAPI and Starlette) here.

    - ApiBusinessError (carries error_code) → business code + default spec message/hint;
    - Plain HTTPException → http_{status} fallback code;
    - Map 404 to A0404 (resource not found) first.
    """
    detail = _detail_str(exc)
    extra = _exc_headers(exc)
    # Business code priority (ApiBusinessError)
    biz_code = getattr(exc, "error_code", None)
    if biz_code and biz_code in CATALOG:
        spec = CATALOG[biz_code]
        return _envelope_spec(spec, message=detail, extra_headers=extra)
    # 404 mapping A0404
    if exc.status_code == 404:
        return _envelope_spec(CATALOG["A0404"], message=detail or "Not Found", extra_headers=extra)
    # The bottom line http_{status}
    return _envelope(
        code=f"http_{exc.status_code}",
        message=detail or "Not Found",
        status=exc.status_code,
        extra_headers=extra,
    )


# ── 5 handler routes ──

async def on_request_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Only log loc and msg: errors() contains the original text of user input (input field) and does not log
    brief = [
        {"loc": ".".join(str(x) for x in e.get("loc", ())), "msg": e.get("msg", "")}
        for e in exc.errors()
    ]
    logger.info("Request verification failed: %s path=%s", brief, request.url.path)
    return _envelope_spec(CATALOG["A0001"])


async def on_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
    return _envelope_from_http_exception(exc)


async def on_starlette_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return _envelope_from_http_exception(exc)  # type: ignore[arg-type]


async def on_unsafe_url(request: Request, exc: UnsafeURLError) -> JSONResponse:
    logger.warning("URL verification failed: %s path=%s", exc, request.url.path)
    return _envelope_spec(CATALOG["A0007"])


async def on_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception path=%s: %s", request.url.path, exc)
    return _envelope_spec(CATALOG["B0001"], message="Internal server error, please try again later")


__all__ = [
    "on_http_exception",
    "on_request_validation",
    "on_starlette_http_exception",
    "on_unsafe_url",
    "on_unhandled_exception",
]
