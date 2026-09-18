"""MiniMax TTS tests for src/realmock/platform/capabilities/voice/tts/providers/minimax.py.

Covers: synthesize_minimax_to_base64 missing-key/empty-text guards, hex/base64/
top-level/missing/non-string audio branches, base/model/voice defaults, HTTP
status/text-read/generic/JSON-decode error branches (HTTP client faked).
Conventions: no real network/model downloads (all clients mocked).
"""
from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from realmock.platform.capabilities.voice.tts.providers import minimax as minimax_mod
from realmock.platform.capabilities.voice.tts.providers.minimax import (
    DEFAULT_BASE,
    DEFAULT_MODEL,
    DEFAULT_VOICE,
    synthesize_minimax_to_base64,
)


def _settings(monkeypatch):
    monkeypatch.setattr(
        minimax_mod, "get_settings", lambda: SimpleNamespace(allow_local_llm=False, is_prod=False)
    )


class _FakeResp:
    def __init__(self, payload=None, raise_exc=None, text="oops"):
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
        self.post_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        self.post_calls.append({"url": url, "headers": headers, "json": json})
        if self._post_exc is not None:
            raise self._post_exc
        return self._resp


def _patch_client(monkeypatch, client):
    monkeypatch.setattr(minimax_mod, "make_pinned_async_client", lambda *a, **k: client)


@pytest.mark.asyncio
async def test_missing_key_returns_empty(monkeypatch):
    _settings(monkeypatch)
    assert await synthesize_minimax_to_base64("hi", api_key="") == ""
    assert await synthesize_minimax_to_base64("hi", api_key="   ") == ""


@pytest.mark.asyncio
async def test_empty_text_returns_empty(monkeypatch):
    _settings(monkeypatch)
    assert await synthesize_minimax_to_base64("", api_key="k") == ""
    assert await synthesize_minimax_to_base64("   ", api_key="k") == ""


@pytest.mark.asyncio
async def test_hex_audio_converted_to_base64(monkeypatch):
    _settings(monkeypatch)
    raw = b"\x01\x02MP3"
    client = _FakeClient(resp=_FakeResp(payload={"data": {"audio": raw.hex()}}))
    _patch_client(monkeypatch, client)
    out = await synthesize_minimax_to_base64("hello", api_key="k")
    assert base64.b64decode(out) == raw
    call = client.post_calls[0]
    assert call["url"] == f"{DEFAULT_BASE}/t2a_v2"
    assert call["headers"]["Authorization"] == "Bearer k"
    assert call["json"]["text"] == "hello"
    assert call["json"]["voice_setting"]["voice_id"] == DEFAULT_VOICE
    assert call["json"]["model"] == DEFAULT_MODEL


@pytest.mark.asyncio
async def test_base_slash_stripped_and_defaults_applied(monkeypatch):
    _settings(monkeypatch)
    raw = b"abc"
    client = _FakeClient(resp=_FakeResp(payload={"data": {"audio": raw.hex()}}))
    _patch_client(monkeypatch, client)
    await synthesize_minimax_to_base64(
        "  hi  ", api_key=" k ", api_base="https://x.example/v1/", model="", voice=""
    )
    call = client.post_calls[0]
    assert call["url"] == "https://x.example/v1/t2a_v2"
    assert call["json"]["model"] == DEFAULT_MODEL
    assert call["json"]["voice_setting"]["voice_id"] == DEFAULT_VOICE
    assert call["json"]["text"] == "hi"


@pytest.mark.asyncio
async def test_full_url_base_used_verbatim(monkeypatch):
    _settings(monkeypatch)
    raw = b"xyz"
    client = _FakeClient(resp=_FakeResp(payload={"data": {"audio": raw.hex()}}))
    _patch_client(monkeypatch, client)
    await synthesize_minimax_to_base64(
        "hi", api_key="k", api_base="https://api.minimaxi.com/v1/t2a_v2"
    )
    assert client.post_calls[0]["url"] == "https://api.minimaxi.com/v1/t2a_v2"


@pytest.mark.asyncio
async def test_generic_mimo_default_voice_maps_to_minimax_default(monkeypatch):
    _settings(monkeypatch)
    raw = b"abc"
    client = _FakeClient(resp=_FakeResp(payload={"data": {"audio": raw.hex()}}))
    _patch_client(monkeypatch, client)
    await synthesize_minimax_to_base64("hi", api_key="k", voice="mimo_default")
    assert client.post_calls[0]["json"]["voice_setting"]["voice_id"] == DEFAULT_VOICE


@pytest.mark.asyncio
async def test_non_hex_audio_passthrough(monkeypatch):
    _settings(monkeypatch)
    b64 = base64.b64encode(b"raw-audio").decode("ascii") + "!!"
    client = _FakeClient(resp=_FakeResp(payload={"data": {"audio": b64}}))
    _patch_client(monkeypatch, client)
    assert await synthesize_minimax_to_base64("hi", api_key="k") == b64


@pytest.mark.asyncio
async def test_top_level_audio_field(monkeypatch):
    _settings(monkeypatch)
    raw = b"top"
    client = _FakeClient(resp=_FakeResp(payload={"audio": raw.hex()}))
    _patch_client(monkeypatch, client)
    out = await synthesize_minimax_to_base64("hi", api_key="k")
    assert base64.b64decode(out) == raw


@pytest.mark.asyncio
async def test_missing_audio_returns_empty(monkeypatch):
    _settings(monkeypatch)
    client = _FakeClient(resp=_FakeResp(payload={"data": {}, "extra": 1}))
    _patch_client(monkeypatch, client)
    assert await synthesize_minimax_to_base64("hi", api_key="k") == ""


@pytest.mark.asyncio
async def test_non_string_audio_returns_empty(monkeypatch):
    _settings(monkeypatch)
    client = _FakeClient(resp=_FakeResp(payload={"data": {"audio": 12345}}))
    _patch_client(monkeypatch, client)
    assert await synthesize_minimax_to_base64("hi", api_key="k") == ""


def _http_status_error(status=500, text="server boom"):
    req = httpx.Request("POST", "https://api.minimaxi.com/v1/t2a_v2")
    resp = httpx.Response(status, text=text, request=req)
    return httpx.HTTPStatusError("err", request=req, response=resp)


@pytest.mark.asyncio
async def test_http_status_error_returns_empty(monkeypatch):
    _settings(monkeypatch)
    client = _FakeClient(post_exc=_http_status_error())
    _patch_client(monkeypatch, client)
    assert await synthesize_minimax_to_base64("hi", api_key="k") == ""


@pytest.mark.asyncio
async def test_http_status_error_text_read_failure(monkeypatch):
    _settings(monkeypatch)

    class _BadTextResp:
        status_code = 502

        @property
        def text(self):
            raise RuntimeError("no body")

    req = httpx.Request("POST", "https://x/v1/t2a_v2")
    exc = httpx.HTTPStatusError("err", request=req, response=_BadTextResp())  # type: ignore[arg-type]
    client = _FakeClient(post_exc=exc)
    _patch_client(monkeypatch, client)
    assert await synthesize_minimax_to_base64("hi", api_key="k") == ""


@pytest.mark.asyncio
async def test_generic_post_exception_returns_empty(monkeypatch):
    _settings(monkeypatch)
    client = _FakeClient(post_exc=RuntimeError("net down"))
    _patch_client(monkeypatch, client)
    assert await synthesize_minimax_to_base64("hi", api_key="k") == ""


@pytest.mark.asyncio
async def test_json_decode_failure_returns_empty(monkeypatch):
    _settings(monkeypatch)
    client = _FakeClient(resp=_FakeResp(payload=ValueError("bad json")))
    # _FakeResp.json raises ValueError which is caught as generic Exception.
    orig_json = client._resp.json

    async def _post(*a, **k):
        r = AsyncMock()
        r.raise_for_status = lambda: None
        r.json = orig_json
        return r

    client.post = _post  # type: ignore[method-assign]
    _patch_client(monkeypatch, client)
    assert await synthesize_minimax_to_base64("hi", api_key="k") == ""


@pytest.mark.asyncio
async def test_overrides_customize_any_body_field(monkeypatch):
    """extras.tts_request deep-merges onto the descriptor defaults."""
    _settings(monkeypatch)
    client = _FakeClient(resp=_FakeResp(payload={"data": {"audio": b"x".hex()}}))
    _patch_client(monkeypatch, client)
    out = await synthesize_minimax_to_base64(
        "hi",
        api_key="k",
        voice="female-shaonv",
        overrides={
            "audio_setting": {"sample_rate": 24000},
            "voice_setting": {"emotion": "calm"},
            "language_boost": "auto",
        },
    )
    assert out
    body = client.post_calls[0]["json"]
    assert body["audio_setting"]["sample_rate"] == 24000
    assert body["audio_setting"]["format"] == "mp3"  # descriptor default survives
    assert body["voice_setting"]["emotion"] == "calm"
    assert body["voice_setting"]["voice_id"] == "female-shaonv"
    assert body["language_boost"] == "auto"
    assert body["model"] == DEFAULT_MODEL


@pytest.mark.asyncio
async def test_base_resp_error_returns_empty(monkeypatch):
    _settings(monkeypatch)
    client = _FakeClient(
        resp=_FakeResp(payload={"base_resp": {"status_code": 1002, "status_msg": "rate limit"}})
    )
    _patch_client(monkeypatch, client)
    assert await synthesize_minimax_to_base64("hi", api_key="k") == ""
    assert client.post_calls  # the request itself happened


@pytest.mark.asyncio
async def test_long_text_splits_at_sentence_boundaries_and_concatenates(monkeypatch):
    _settings(monkeypatch)
    text = "第一句话内容足够长。\n第二段也有实际内容，可以独立成段。"
    limit = 10  # force multiple chunks below the real descriptor limit
    monkeypatch.setattr(minimax_mod, "_capability_def", lambda: {"limits": {"chunk_chars": limit}, "request": {}, "response": {}})
    parts = [b"part-one", b"part-two", b"part-three"]

    async def _fake_chunk(body, url, api_key):
        return base64.b64encode(parts.pop(0)).decode("ascii")

    monkeypatch.setattr(minimax_mod, "_synthesize_chunk", _fake_chunk)
    out = await synthesize_minimax_to_base64(text, api_key="k")
    assert base64.b64decode(out) == b"".join(
        [b"part-one", b"part-two", b"part-three"]
    )


def test_split_text_chunks_respects_limit_and_paragraphs():
    chunks = minimax_mod.split_text_chunks("短句。", 100)
    assert chunks == ["短句。"]
    long_text = "。" .join(["一句话" * 30] * 6) + "。"
    for chunk in minimax_mod.split_text_chunks(long_text, 200):
        assert len(chunk) <= 200
    joined = "".join(minimax_mod.split_text_chunks(long_text, 200))
    assert joined.replace("。", "") == long_text.replace("。", "")


_PROSODY_DEF: dict = {
    "request": {"body": {"stream": False, "voice_setting": {"speed": 1.0, "vol": 1.0, "pitch": 0}}},
    "response": {},
    "prosody": {
        "emotion_map": {"neutral": "", "smile": "happy", "serious": "calm", "sad": "sad"},
        "speed": {"base": 1.0, "min": 0.5, "max": 2.0},
        "pitch": {"min": -12, "max": 12},
    },
}


def test_build_tts_body_emotion_maps_to_native(monkeypatch):
    monkeypatch.setattr(minimax_mod, "_capability_def", lambda: _PROSODY_DEF)
    body = minimax_mod.build_tts_body("hi", model="m", voice="v", emotion="smile")
    assert body["voice_setting"]["emotion"] == "happy"
    body = minimax_mod.build_tts_body("hi", model="m", voice="v", emotion="serious")
    assert body["voice_setting"]["emotion"] == "calm"
    # neutral maps to "" → no emotion key; descriptor/override values survive
    body = minimax_mod.build_tts_body("hi", model="m", voice="v", emotion="neutral")
    assert "emotion" not in body["voice_setting"]
    # unknown emotion → no mapping applied
    body = minimax_mod.build_tts_body("hi", model="m", voice="v", emotion="excited")
    assert "emotion" not in body["voice_setting"]


def test_build_tts_body_neutral_keeps_static_overrides(monkeypatch):
    monkeypatch.setattr(minimax_mod, "_capability_def", lambda: _PROSODY_DEF)
    body = minimax_mod.build_tts_body(
        "hi",
        model="m",
        voice="v",
        overrides={"voice_setting": {"emotion": "whisper", "speed": 1.2}},
    )
    assert body["voice_setting"]["emotion"] == "whisper"
    assert body["voice_setting"]["speed"] == 1.2


def test_build_tts_body_rate_maps_to_speed_with_clamp(monkeypatch):
    monkeypatch.setattr(minimax_mod, "_capability_def", lambda: _PROSODY_DEF)
    body = minimax_mod.build_tts_body("hi", model="m", voice="v", rate="+12%")
    assert body["voice_setting"]["speed"] == 1.12
    body = minimax_mod.build_tts_body("hi", model="m", voice="v", rate="-50%")
    assert body["voice_setting"]["speed"] == 0.5  # clamped low
    body = minimax_mod.build_tts_body("hi", model="m", voice="v", rate="+200%")
    assert body["voice_setting"]["speed"] == 2.0  # clamped high
    body = minimax_mod.build_tts_body("hi", model="m", voice="v", rate="+0%")
    assert body["voice_setting"]["speed"] == 1.0  # untouched default
    body = minimax_mod.build_tts_body("hi", model="m", voice="v", rate="bogus")
    assert body["voice_setting"]["speed"] == 1.0


def test_build_tts_body_pitch_offset_and_clamp(monkeypatch):
    monkeypatch.setattr(minimax_mod, "_capability_def", lambda: _PROSODY_DEF)
    body = minimax_mod.build_tts_body("hi", model="m", voice="v", pitch="+3Hz")
    assert body["voice_setting"]["pitch"] == 3
    body = minimax_mod.build_tts_body(
        "hi",
        model="m",
        voice="v",
        pitch="+20Hz",
        overrides={"voice_setting": {"pitch": 10}},
    )
    assert body["voice_setting"]["pitch"] == 12  # clamped from 10+20
    body = minimax_mod.build_tts_body("hi", model="m", voice="v", pitch="+0Hz")
    assert body["voice_setting"]["pitch"] == 0


def test_build_tts_body_without_prosody_section_is_noop(monkeypatch):
    monkeypatch.setattr(
        minimax_mod, "_capability_def", lambda: {"request": {"body": {"voice_setting": {}}}, "response": {}}
    )
    body = minimax_mod.build_tts_body(
        "hi", model="m", voice="v", emotion="smile", rate="+12%", pitch="+3Hz"
    )
    assert "emotion" not in body["voice_setting"]
    assert "speed" not in body["voice_setting"]
    assert "pitch" not in body["voice_setting"]


@pytest.mark.asyncio
async def test_synthesize_passes_prosody_into_request(monkeypatch):
    _settings(monkeypatch)
    seen: list[dict] = []

    def _fake_build(text, *, model, voice, overrides, emotion, rate, pitch):
        seen.append({"emotion": emotion, "rate": rate, "pitch": pitch})
        return {"voice_setting": {}, "text": text, "model": model}

    monkeypatch.setattr(minimax_mod, "build_tts_body", _fake_build)

    async def _fake_chunk(body, url, api_key):
        return base64.b64encode(b"a").decode("ascii")

    monkeypatch.setattr(minimax_mod, "_synthesize_chunk", _fake_chunk)
    await synthesize_minimax_to_base64(
        "hi", api_key="k", emotion="smile", rate="+5%", pitch="+2Hz"
    )
    assert seen == [{"emotion": "smile", "rate": "+5%", "pitch": "+2Hz"}]
