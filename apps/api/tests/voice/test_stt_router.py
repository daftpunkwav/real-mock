"""STT router tests for src/realmock/platform/capabilities/voice/stt/router.py.

Covers: transcribe_with_handler empty-audio, coming-soon fallback, native-audio
fallback, openai-chat mimo, unknown-provider local fallback, primary-exception
with mode none, primary-empty to configured handler, fallback-exception swallow,
unknown-handler, primary-success, text-only branches (providers faked).
Conventions: no real network/model downloads (all clients mocked); fake providers;
rate limits reset per test.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

import realmock.platform.capabilities.voice.stt.router as router_mod
from realmock.platform.capabilities.voice.stt.base import SttCredentials


def _fake_provider(ret=None, exc=None):
    if exc is not None:
        return type("_P", (), {"transcribe": AsyncMock(side_effect=exc)})()
    return type("_P", (), {"transcribe": AsyncMock(return_value=ret)})()


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()


def _creds(**over) -> SttCredentials:
    base = {
        "provider": "local",
        "protocol": "openai_chat",
        "fallback_handler": "local",
        "fallback_mode": "transcribe",
    }
    base.update(over)
    return SttCredentials(**base)


@pytest.mark.asyncio
async def test_empty_pcm_returns_local_empty() -> None:
    out = await router_mod.transcribe_with_handler("", sample_rate=16000, creds=_creds())
    assert out.text == ""
    assert out.provider == "local"


@pytest.mark.asyncio
async def test_coming_soon_forces_local_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        router_mod, "find_provider", lambda stage, pid: {"status": "coming_soon"}
    )
    fake_local = _fake_provider("local-text")
    monkeypatch.setitem(router_mod._PROVIDERS, "local", fake_local)
    out = await router_mod.transcribe_with_handler(
        "AAA", sample_rate=16000, creds=_creds(provider="zhipu_glm4_voice")
    )
    assert out.text == "local-text"
    assert out.provider == "local"
    assert out.fallback is True
    assert out.requested_provider == "zhipu_glm4_voice"


@pytest.mark.asyncio
async def test_native_audio_not_ready_falls_back(monkeypatch) -> None:
    monkeypatch.setattr(
        router_mod,
        "find_provider",
        lambda stage, pid: {"recognize_via": "native_audio", "status": "active"},
    )
    fake_local = _fake_provider("native-fallback")
    monkeypatch.setitem(router_mod._PROVIDERS, "local", fake_local)
    out = await router_mod.transcribe_with_handler(
        "AAA", sample_rate=16000, creds=_creds(provider="doubao_s2s")
    )
    assert out.provider == "local"
    assert out.text == "native-fallback"
    assert out.fallback is True


@pytest.mark.asyncio
async def test_openai_chat_unknown_provider_uses_mimo(monkeypatch) -> None:
    monkeypatch.setattr(router_mod, "find_provider", lambda stage, pid: None)
    fake_mimo = _fake_provider("mimo-text")
    monkeypatch.setitem(router_mod._PROVIDERS, "mimo_audio", fake_mimo)
    out = await router_mod.transcribe_with_handler(
        "AAA",
        sample_rate=16000,
        creds=_creds(provider="custom_xyz", protocol="openai_chat"),
    )
    assert out.text == "mimo-text"
    assert out.provider == "custom_xyz"
    assert out.fallback is False


@pytest.mark.asyncio
async def test_unknown_provider_falls_back_to_local(monkeypatch) -> None:
    monkeypatch.setattr(router_mod, "find_provider", lambda stage, pid: None)
    fake_local = _fake_provider("hello")
    monkeypatch.setitem(router_mod._PROVIDERS, "local", fake_local)
    out = await router_mod.transcribe_with_handler(
        "AAA", sample_rate=16000, creds=_creds(provider="nope", protocol="other")
    )
    assert out.text == "hello"
    assert out.provider == "local"
    assert out.fallback is True


@pytest.mark.asyncio
async def test_primary_exception_then_fallback_mode_none(monkeypatch) -> None:
    monkeypatch.setattr(router_mod, "find_provider", lambda stage, pid: None)
    boom = _fake_provider(exc=RuntimeError("asr down"))
    monkeypatch.setitem(router_mod._PROVIDERS, "local", boom)
    out = await router_mod.transcribe_with_handler(
        "AAA",
        sample_rate=16000,
        creds=_creds(provider="local", fallback_mode="none"),
    )
    assert out.text == ""
    assert out.fallback is True


@pytest.mark.asyncio
async def test_primary_empty_falls_back_to_configured_handler(monkeypatch) -> None:
    monkeypatch.setattr(router_mod, "find_provider", lambda stage, pid: None)

    class _Primary:
        async def transcribe(self, *a, **k):
            return ""

    class _Fallback:
        async def transcribe(self, *a, **k):
            return "fallback-text"

    monkeypatch.setitem(router_mod._PROVIDERS, "local", _Primary())
    monkeypatch.setitem(router_mod._PROVIDERS, "volcengine", _Fallback())
    out = await router_mod.transcribe_with_handler(
        "AAA",
        sample_rate=16000,
        creds=_creds(provider="local", fallback_handler="volcengine"),
        fallback_local=True,
    )
    # requested == local, fallback_handler differs; primary empty so fallback runs
    assert out.text == "fallback-text"
    assert out.provider == "volcengine"
    assert out.fallback is True


@pytest.mark.asyncio
async def test_fallback_exception_is_swallowed(monkeypatch) -> None:
    monkeypatch.setattr(router_mod, "find_provider", lambda stage, pid: None)

    class _Primary:
        async def transcribe(self, *a, **k):
            return ""

    class _BadFallback:
        async def transcribe(self, *a, **k):
            raise RuntimeError("fallback down")

    monkeypatch.setitem(router_mod._PROVIDERS, "xfyun", _Primary())
    monkeypatch.setitem(router_mod._PROVIDERS, "volcengine", _BadFallback())
    out = await router_mod.transcribe_with_handler(
        "AAA",
        sample_rate=16000,
        creds=_creds(provider="xfyun", fallback_handler="volcengine"),
    )
    assert out.text == ""
    assert out.provider == "volcengine"
    assert out.fallback is True


@pytest.mark.asyncio
async def test_unknown_fallback_handler_reports_primary(monkeypatch) -> None:
    monkeypatch.setattr(router_mod, "find_provider", lambda stage, pid: None)

    class _Primary:
        async def transcribe(self, *a, **k):
            return ""

    monkeypatch.setitem(router_mod._PROVIDERS, "xfyun", _Primary())
    # fallback_handler unknown -> not in _PROVIDERS
    out = await router_mod.transcribe_with_handler(
        "AAA",
        sample_rate=16000,
        creds=_creds(provider="xfyun", fallback_handler="ghost_xyz"),
    )
    assert out.text == ""
    assert out.provider == "xfyun"
    assert out.fallback is True


@pytest.mark.asyncio
async def test_primary_success_no_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        router_mod, "find_provider", lambda stage, pid: {"status": "ready"}
    )
    fake = _fake_provider("direct")
    monkeypatch.setitem(router_mod._PROVIDERS, "xfyun", fake)
    out = await router_mod.transcribe_with_handler(
        "AAA", sample_rate=16000, creds=_creds(provider="xfyun")
    )
    assert out.text == "direct"
    assert out.provider == "xfyun"
    assert out.fallback is False


@pytest.mark.asyncio
async def test_text_only_mode_skips_fallback(monkeypatch) -> None:
    monkeypatch.setattr(router_mod, "find_provider", lambda stage, pid: None)

    class _Primary:
        async def transcribe(self, *a, **k):
            return ""

    monkeypatch.setitem(router_mod._PROVIDERS, "xfyun", _Primary())
    with patch.object(router_mod, "_PROVIDERS", router_mod._PROVIDERS):
        out = await router_mod.transcribe_with_handler(
            "AAA",
            sample_rate=16000,
            creds=_creds(provider="xfyun", fallback_mode="text_only"),
        )
    assert out.text == ""
    assert out.fallback is True
