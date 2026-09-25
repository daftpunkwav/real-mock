"""Shared fixtures for growth-domain tests (sessions-side insight table)."""

from __future__ import annotations

import pytest


@pytest.fixture
def insight_table(engine):
    import realmock.domains.growth.models.insight  # noqa: F401
    from realmock.platform.database import SessionsBase

    SessionsBase.metadata.create_all(bind=engine)
    yield
