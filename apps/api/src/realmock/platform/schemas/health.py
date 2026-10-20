"""Liveness probe contract."""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Payload of the ``GET /health`` probe.

    Declared as a model so the OpenAPI contract states the shape instead of
    leaving it as an untyped object.
    """

    status: str
    service: str
    version: str
