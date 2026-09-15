"""Main entry tests for realmock.domains.prep.main.

Covers: app export and _bootstrap delegation
Conventions: bootstrap_databases_and_seed faked; no real DB; rate limits reset per test
"""
from __future__ import annotations
import pytest

@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()

def test_prep_main_entry(monkeypatch) -> None:
    import asyncio

    import realmock.domains.prep.main as main_mod

    assert main_mod.app is not None
    assert main_mod.__all__ == ["app"]
    called: dict = {}

    def _fake_bootstrap(*args, **kwargs):
        called["ok"] = True

    monkeypatch.setattr(main_mod, "bootstrap_databases_and_seed", _fake_bootstrap)
    asyncio.run(main_mod._bootstrap())
    assert called.get("ok") is True
