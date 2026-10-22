"""Liveness probe contract."""

from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    # Payload of the ``GET /health`` probe: the liveness answer of the service.
    # Documented as comments on purpose: a docstring would be published as the
    # schema description, and the contract must state the payload, not how the
    # backend declares it.
    status: str
    service: str
    version: str
