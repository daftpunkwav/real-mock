"""Availability tests for realmock.domains.prep.agents.tools.system.availability.

Covers: tool_available and preload_secondary exception/unknown branches
Conventions: Availability table patched; no I/O; rate limits reset per test
"""
from __future__ import annotations
import pytest

@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()

def test_tool_available_exception_returns_true(monkeypatch) -> None:
    import realmock.domains.prep.agents.tools.system.availability as avail_mod

    monkeypatch.setitem(avail_mod._TOOL_AVAILABILITY, "boom_tool", lambda *a: 1 / 0)
    assert avail_mod.tool_available("boom_tool", "hi", None) is True

def test_preload_secondary_exception_returns_false(monkeypatch) -> None:
    import realmock.domains.prep.agents.tools.system.availability as avail_mod

    monkeypatch.setitem(avail_mod._TOOL_AVAILABILITY, "boom2", lambda *a: 1 / 0)
    assert avail_mod.preload_secondary("boom2", "hi", None) is False
    assert avail_mod.preload_secondary("unknown_xyz", "hi", None) is False
    assert avail_mod.tool_available("unknown_xyz", "hi", None) is True
