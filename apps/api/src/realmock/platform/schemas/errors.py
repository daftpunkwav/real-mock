"""Unified API error envelope."""

from __future__ import annotations

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    trace_id: str = ""


class APIError(BaseModel):
    """Unify the error response shape and align it one by one with the envelope of the aggregation entry."""

    model_config = {"extra": "forbid"}

    detail: str | None = None
    error: ErrorBody | None = None
