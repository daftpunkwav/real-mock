"""Unified API error envelope (registered as an OpenAPI component by the app factory).

Every JSON error response is emitted by the shared handlers in
``realmock.platform.core.error_handlers._envelope``; this model is the
schema-level mirror of that wire shape.
"""

from __future__ import annotations

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    hint: str = ""
    retryable: bool = False
    trace_id: str = ""


# Unify the error response shape and align it one by one with the envelope of the aggregation entry.
class APIError(BaseModel):
    model_config = {"extra": "forbid"}

    detail: str
    error: ErrorBody
