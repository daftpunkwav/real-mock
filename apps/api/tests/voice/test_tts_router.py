"""TTS router tests for src/realmock/platform/capabilities/voice/tts/__init__.py.

Covers: synthesize_speech/synthesize_primary_speech text-only/none/coming-soon/
native-audio branches, handler success/exception/fallback paths, _synthesize_handler
none/edge/minimax/custom branches, _synthesize_fallback guardrails, _synthesize_openai_compat
protocol/creds/payload/audio/error branches, synthesize_custom_speech.
Conventions: no real network/model downloads (all clients mocked).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

import importlib

from realmock.platform.capabilities.voice.tts import (
    TtsCredentials,
    synthesize_custom_speech,
    synthesize_primary_speech,
    synthesize_speech,
)

tts_mod = importlib.import_module("realmock.platform.capabilities.voice.tts")


def _settings(monkeypatch):
    monkeypatch.setattr(
        tts_mod, "get_settings", lambda: SimpleNamespace(allow_local_llm=False, is_prod=False)
    )


class _FakeResp:
    def __init__(self, payload=None, raise_exc=None, text="err"):
        self._payload = payload
        self._raise_exc = raise_exc
        self.text = text

    def raise_for_status(self):
        if self._raise_exc is not None:
            raise self._raise_exc

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _FakeClient:
    def __init__(self, resp=None, post_exc=None):
        self._resp = resp
        self._post_exc = post_exc
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        if self._post_exc is not None:
            raise self._post_exc
        return self._resp


def _http_status_error():
    req = httpx.Request("POST", "https://x/chat/completions")
    resp = httpx.Response(500, text="tts boom", request=req)
    return httpx.HTTPStatusError("e", request=req, response=resp)


@pytest.mark.asyncio
async def test_text_only_and_none_short_circuit():
    assert (
        await synthesize_speech("hi", creds=TtsCredentials(handler="edge", mode="text_only")) == ""
    )
    assert await synthesize_speech("hi", creds=TtsCredentials(handler="none")) == ""
    assert await synthesize_primary_speech("hi", creds=TtsCredentials(handler="none")) == ""
    assert (
        await synthesize_primary_speech(
            "hi", creds=TtsCredentials(handler="edge", mode="text_only")
        )
        == ""
    )


@pytest.mark.asyncio
async def test_coming_soon_falls_back_to_edge():
    creds = TtsCredentials(handler="zhipu_glm4_voice", mode="tts_from_text")
    with (
        patch.object(tts_mod, "edge_synthesize", new=AsyncMock(return_value="EDGE")) as edge,
    ):
        out = await synthesize_speech("hi", creds=creds)
    assert out == "EDGE"
    edge.assert_awaited()


@pytest.mark.asyncio
async def test_coming_soon_without_fallback_returns_empty():
    creds = TtsCredentials(
        handler="zhipu_glm4_voice", mode="tts_from_text", fallback_handler="none"
    )
    with patch.object(tts_mod, "edge_synthesize", new=AsyncMock(return_value="EDGE")):
        assert await synthesize_speech("hi", creds=creds) == ""


@pytest.mark.asyncio
async def test_native_audio_goes_to_fallback():
    creds = TtsCredentials(handler="edge", mode="native_audio", fallback_handler="edge")
    # Same handler as fallback -> no recursion, returns "".
    assert await synthesize_speech("hi", creds=creds) == ""
    assert await synthesize_primary_speech("hi", creds=creds) == ""


@pytest.mark.asyncio
async def test_primary_coming_soon_and_native_return_empty():
    assert (
        await synthesize_primary_speech(
            "hi", creds=TtsCredentials(handler="zhipu_glm4_voice", mode="tts_from_text")
        )
        == ""
    )
    assert (
        await synthesize_primary_speech(
            "hi", creds=TtsCredentials(handler="edge", mode="native_audio")
        )
        == ""
    )


@pytest.mark.asyncio
async def test_primary_success_and_exception():
    with patch.object(tts_mod, "edge_synthesize", new=AsyncMock(return_value="A")):
        assert await synthesize_primary_speech("hi", creds=TtsCredentials(handler="edge")) == "A"
    with patch.object(tts_mod, "edge_synthesize", new=AsyncMock(side_effect=RuntimeError("x"))):
        # _synthesize_handler catches edge errors -> "" (no fallback in primary path).
        assert await synthesize_primary_speech("hi", creds=TtsCredentials(handler="edge")) == ""
    with patch.object(
        tts_mod, "_synthesize_handler", new=AsyncMock(side_effect=RuntimeError("boom"))
    ):
        assert await synthesize_primary_speech("hi", creds=TtsCredentials(handler="custom")) == ""


@pytest.mark.asyncio
async def test_handler_success_no_fallback():
    with patch.object(tts_mod, "edge_synthesize", new=AsyncMock(return_value="OK")):
        out = await synthesize_speech("hi", creds=TtsCredentials(handler="edge"))
    assert out == "OK"


@pytest.mark.asyncio
async def test_handler_exception_then_fallback_edge():
    with (
        patch.object(tts_mod, "edge_synthesize", new=AsyncMock(return_value="FB")),
        patch.object(tts_mod, "find_provider", return_value=None),
    ):
        # Primary custom returns "" so fallback to edge is exercised.
        with patch.object(tts_mod, "_synthesize_openai_compat", new=AsyncMock(return_value="")):
            out = await synthesize_speech(
                "hi",
                creds=TtsCredentials(
                    handler="custom",
                    mode="tts_from_text",
                    api_base="https://x",
                    api_key="k",
                    fallback_handler="edge",
                    fallback_mode="tts_from_text",
                ),
            )
        assert out == "FB"


@pytest.mark.asyncio
async def test_handler_raises_then_fallback():
    with (
        patch.object(
            tts_mod, "_synthesize_handler", new=AsyncMock(side_effect=[RuntimeError("boom"), "FB2"])
        ),
    ):
        out = await synthesize_speech("hi", creds=TtsCredentials(handler="custom"))
    assert out == "FB2"


@pytest.mark.asyncio
async def test_handler_empty_result_triggers_fallback():
    with (
        patch.object(tts_mod, "_synthesize_handler", new=AsyncMock(side_effect=["", "FALLBACK"])),
    ):
        out = await synthesize_speech("hi", creds=TtsCredentials(handler="custom"))
    assert out == "FALLBACK"


@pytest.mark.asyncio
async def test_synthesize_handler_none_and_edge_variants():
    assert (
        await tts_mod._synthesize_handler(
            "hi", TtsCredentials(handler="none"), "none", rate="+0%", pitch="+0Hz"
        )
        == ""
    )
    with patch.object(tts_mod, "edge_synthesize", new=AsyncMock(return_value="E")) as m:
        assert (
            await tts_mod._synthesize_handler(
                "hi", TtsCredentials(voice=""), "edge", rate="+0%", pitch="+0Hz"
            )
            == "E"
        )
        assert m.await_args.args[1] == "zh-CN-XiaoxiaoNeural"
    with patch.object(tts_mod, "edge_synthesize", new=AsyncMock(side_effect=RuntimeError("e"))):
        assert (
            await tts_mod._synthesize_handler(
                "hi", TtsCredentials(), "edge", rate="+0%", pitch="+0Hz"
            )
            == ""
        )


@pytest.mark.asyncio
async def test_synthesize_handler_minimax_delegation():
    creds = TtsCredentials(handler="minimax_speech", api_key="k", api_base="", model="", voice="")
    with patch.object(
        tts_mod, "synthesize_minimax_to_base64", new=AsyncMock(return_value="M")
    ) as m:
        assert (
            await tts_mod._synthesize_handler(
                "hi", creds, "minimax_speech", rate="+0%", pitch="+0Hz"
            )
            == "M"
        )
        assert m.await_args.kwargs["api_base"] == tts_mod.MINIMAX_DEFAULT_BASE
        assert m.await_args.kwargs["model"] == tts_mod.MINIMAX_DEFAULT_MODEL
        assert m.await_args.kwargs["voice"] == tts_mod.MINIMAX_DEFAULT_VOICE


@pytest.mark.asyncio
async def test_synthesize_handler_custom_delegates_openai(monkeypatch):
    _settings(monkeypatch)
    client = _FakeClient(
        resp=_FakeResp(payload={"choices": [{"message": {"audio": {"data": "B64"}}}]})
    )
    monkeypatch.setattr(tts_mod, "make_pinned_async_client", lambda *a, **k: client)
    out = await tts_mod._synthesize_handler(
        "hi",
        TtsCredentials(handler="custom", api_base="https://x", api_key="k"),
        "custom",
        rate="+0%",
        pitch="+0Hz",
    )
    assert out == "B64"


@pytest.mark.asyncio
async def test_fallback_guardrails():
    # Same handler -> no fallback.
    assert (
        await tts_mod._synthesize_fallback(
            "hi", TtsCredentials(handler="edge", fallback_handler="edge"), rate="+0%", pitch="+0Hz"
        )
        == ""
    )
    assert (
        await tts_mod._synthesize_fallback(
            "hi", TtsCredentials(fallback_handler=""), rate="+0%", pitch="+0Hz"
        )
        == ""
    )
    assert (
        await tts_mod._synthesize_fallback(
            "hi", TtsCredentials(fallback_handler="none"), rate="+0%", pitch="+0Hz"
        )
        == ""
    )
    assert (
        await tts_mod._synthesize_fallback(
            "hi", TtsCredentials(fallback_handler="text_only"), rate="+0%", pitch="+0Hz"
        )
        == ""
    )
    assert (
        await tts_mod._synthesize_fallback(
            "hi",
            TtsCredentials(handler="edge", fallback_handler="custom", fallback_mode="text_only"),
            rate="+0%",
            pitch="+0Hz",
        )
        == ""
    )


@pytest.mark.asyncio
async def test_fallback_uses_edge_default_voice():
    with patch.object(tts_mod, "edge_synthesize", new=AsyncMock(return_value="E2")) as m:
        out = await tts_mod._synthesize_fallback(
            "hi",
            TtsCredentials(handler="custom", voice="keep-me", fallback_handler="edge"),
            rate="+0%",
            pitch="+0Hz",
        )
    assert out == "E2"
    assert m.await_args.args[1] == tts_mod.EDGE_DEFAULT_VOICE


@pytest.mark.asyncio
async def test_fallback_keeps_custom_voice():
    with patch.object(tts_mod, "_synthesize_openai_compat", new=AsyncMock(return_value="C2")):
        out = await tts_mod._synthesize_fallback(
            "hi",
            TtsCredentials(
                handler="edge",
                voice="v1",
                api_base="https://x",
                api_key="k",
                fallback_handler="custom",
            ),
            rate="+0%",
            pitch="+0Hz",
        )
    assert out == "C2"


@pytest.mark.asyncio
async def test_openai_compat_wrong_protocol(monkeypatch):
    _settings(monkeypatch)
    assert await tts_mod._synthesize_openai_compat("hi", TtsCredentials(protocol="other")) == ""


@pytest.mark.asyncio
async def test_openai_compat_missing_creds(monkeypatch):
    _settings(monkeypatch)
    assert (
        await tts_mod._synthesize_openai_compat("hi", TtsCredentials(api_key="", api_base="")) == ""
    )
    assert (
        await tts_mod._synthesize_openai_compat("hi", TtsCredentials(api_key="k", api_base=""))
        == ""
    )


@pytest.mark.asyncio
async def test_openai_compat_success_and_payload(monkeypatch):
    _settings(monkeypatch)
    client = _FakeClient(
        resp=_FakeResp(payload={"choices": [{"message": {"audio": {"data": "AUD"}}}]})
    )
    monkeypatch.setattr(tts_mod, "make_pinned_async_client", lambda *a, **k: client)
    out = await tts_mod._synthesize_openai_compat(
        "hello", TtsCredentials(api_base="https://x/", api_key=" k ", model="", voice="")
    )
    assert out == "AUD"
    call = client.calls[0]
    assert call["url"] == "https://x/chat/completions"
    assert call["json"]["model"] == "mimo-v2.5-tts"
    assert call["json"]["audio"]["voice"] == "mimo_default"
    assert call["headers"]["Authorization"] == "Bearer k"


@pytest.mark.asyncio
async def test_openai_compat_no_audio_variants(monkeypatch):
    _settings(monkeypatch)
    for payload in [
        {},
        {"choices": []},
        {"choices": [{"message": {}}]},
        {"choices": [{"message": {"audio": {}}}]},
    ]:
        client = _FakeClient(resp=_FakeResp(payload=payload))
        monkeypatch.setattr(tts_mod, "make_pinned_async_client", lambda *a, **k: client)
        assert (
            await tts_mod._synthesize_openai_compat(
                "hi", TtsCredentials(api_base="https://x", api_key="k")
            )
            == ""
        )


@pytest.mark.asyncio
async def test_openai_compat_http_and_generic_errors(monkeypatch):
    _settings(monkeypatch)
    client = _FakeClient(post_exc=_http_status_error())
    monkeypatch.setattr(tts_mod, "make_pinned_async_client", lambda *a, **k: client)
    assert (
        await tts_mod._synthesize_openai_compat(
            "hi", TtsCredentials(api_base="https://x", api_key="k")
        )
        == ""
    )
    client2 = _FakeClient(post_exc=RuntimeError("down"))
    monkeypatch.setattr(tts_mod, "make_pinned_async_client", lambda *a, **k: client2)
    assert (
        await tts_mod._synthesize_openai_compat(
            "hi", TtsCredentials(api_base="https://x", api_key="k")
        )
        == ""
    )


@pytest.mark.asyncio
async def test_synthesize_custom_speech_no_fallback(monkeypatch):
    _settings(monkeypatch)
    client = _FakeClient(
        resp=_FakeResp(payload={"choices": [{"message": {"audio": {"data": "Z"}}}]})
    )
    monkeypatch.setattr(tts_mod, "make_pinned_async_client", lambda *a, **k: client)
    assert (
        await synthesize_custom_speech(
            "hi", creds=TtsCredentials(api_base="https://x", api_key="k")
        )
        == "Z"
    )
