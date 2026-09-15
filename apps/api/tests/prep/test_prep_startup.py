"""Startup tests for realmock.domains.prep.startup.

Covers: SESSION_DOMAINS constant
Conventions: No I/O; import-only check; rate limits reset per test
"""
from __future__ import annotations
import pytest

@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()

def test_prep_startup_constant() -> None:
    from realmock.domains.prep.startup import SESSION_DOMAINS

    assert SESSION_DOMAINS == ("prep",)
