"""Model-test route tests for realmock.domains.settings.routes.model_tests.

Covers: audio-in, audio-out, and reason dispatch branches.
Conventions: profile/test helpers stubbed; no network or DB.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from realmock.platform.core.ratelimit import reset_rate_limit


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()


@pytest.mark.asyncio
async def test_model_audio_in_branch(monkeypatch) -> None:
    import importlib

    mod = importlib.import_module("realmock.domains.settings.routes.model_tests")
    monkeypatch.setattr(
        mod, "get_profile", lambda db, mid: SimpleNamespace(cap_audio_in=True)
    )
    monkeypatch.setattr(mod, "test_recognize", lambda db, profile_id: "rec")
    monkeypatch.setattr(mod, "run_timed_stage_test", AsyncMock(return_value={"ok": 1}))
    out = await mod.test_model(1, db=MagicMock())
    assert out == {"ok": 1}


@pytest.mark.asyncio
async def test_model_audio_out_branch(monkeypatch) -> None:
    import importlib

    mod = importlib.import_module("realmock.domains.settings.routes.model_tests")
    monkeypatch.setattr(
        mod,
        "get_profile",
        lambda db, mid: SimpleNamespace(cap_audio_in=False, cap_audio_out=True),
    )
    monkeypatch.setattr(mod, "test_speak", lambda db, profile_id: "spk")
    monkeypatch.setattr(mod, "run_timed_stage_test", AsyncMock(return_value={"ok": 2}))
    out = await mod.test_model(2, db=MagicMock())
    assert out == {"ok": 2}


@pytest.mark.asyncio
async def test_model_reason_branch(monkeypatch) -> None:
    import importlib

    mod = importlib.import_module("realmock.domains.settings.routes.model_tests")
    monkeypatch.setattr(
        mod,
        "get_profile",
        lambda db, mid: SimpleNamespace(cap_audio_in=False, cap_audio_out=False),
    )
    monkeypatch.setattr(mod, "test_reason", lambda db, profile_id: "rsn")
    monkeypatch.setattr(mod, "run_timed_stage_test", AsyncMock(return_value={"ok": 3}))
    out = await mod.test_model(3, db=MagicMock())
    assert out == {"ok": 3}
