"""MiniMax TTS tests for src/realmock/platform/capabilities/voice/tts/minimax.py.

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

from realmock.platform.capabilities.voice.tts import minimax as minimax_mod
from realmock.platform.capabilities.voice.tts.minimax import (
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
