"""MiniMax STT tests for src/realmock/platform/capabilities/voice/stt/providers/minimax.py.

Covers: missing key/base guards, too-short audio guard, verbatim full-URL vs
appended path, multipart fields (model/response_format/file/language), text
parsing incl. short/empty text, HTTP and generic error branches (HTTP client faked).
Conventions: no real network/model downloads (all clients mocked).
"""
from __future__ import annotations

import base64
from types import SimpleNamespace

import httpx
import pytest

from realmock.platform.capabilities.voice.stt.base import SttCredentials
from realmock.platform.capabilities.voice.stt.providers.minimax import (
    DEFAULT_MODEL,
    MiniMaxSttProvider,
)
from realmock.platform.capabilities.voice.stt.providers import minimax as minimax_stt_mod

# 1s of int16 mono silence @16k — passes the min-duration guard, wav wrapping is pure bytes.
_PCM_B64 = base64.b64encode(b"\x00\x00" * 16000).decode("ascii")


def _settings(monkeypatch):
    monkeypatch.setattr(
        minimax_stt_mod, "get_settings", lambda: SimpleNamespace(allow_local_llm=False, is_prod=False)
    )


def _creds(**over) -> SttCredentials:
    base = {
        "provider": "MiniMax-语音识别",
        "api_base": "https://api.minimaxi.com/v1",
        "api_key": "k",
        "model": "",
    }
    base.update(over)
    return SttCredentials(**base)


class _FakeResp:
    def __init__(self, payload=None, raise_exc=None):
        self._payload = payload
        self._raise_exc = raise_exc

    def raise_for_status(self):
        if self._raise_exc is not None:
            raise self._raise_exc

    def json(self):
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

    async def post(self, url, headers=None, data=None, files=None):
        self.post_calls.append({"url": url, "headers": headers, "data": data, "files": files})
        if self._post_exc is not None:
            raise self._post_exc
        return self._resp


def _patch_client(monkeypatch, client):
    monkeypatch.setattr(minimax_stt_mod, "make_pinned_async_client", lambda *a, **k: client)


@pytest.mark.asyncio
async def test_missing_key_or_base_returns_empty(monkeypatch):
    _settings(monkeypatch)
    provider = MiniMaxSttProvider()
    assert await provider.transcribe(_PCM_B64, sample_rate=16000, creds=_creds(api_key="")) == ""
    assert await provider.transcribe(_PCM_B64, sample_rate=16000, creds=_creds(api_base="")) == ""


@pytest.mark.asyncio
async def test_too_short_audio_returns_empty(monkeypatch):
    _settings(monkeypatch)
    short = base64.b64encode(b"\x00\x00" * 1600).decode("ascii")  # 0.1s
    provider = MiniMaxSttProvider()
    assert await provider.transcribe(short, sample_rate=16000, creds=_creds()) == ""


@pytest.mark.asyncio
async def test_full_url_mode_posts_verbatim_with_multipart(monkeypatch):
    _settings(monkeypatch)
    client = _FakeClient(resp=_FakeResp(payload={"text": "同比前年增长五成"}))
    _patch_client(monkeypatch, client)
    provider = MiniMaxSttProvider()
    out = await provider.transcribe(
        _PCM_B64,
        sample_rate=16000,
        creds=_creds(
            api_base="https://api.minimaxi.com/v1/speech_to_text",
            full_url=True,
        ),
    )
    assert out == "同比前年增长五成"
    call = client.post_calls[0]
    assert call["url"] == "https://api.minimaxi.com/v1/speech_to_text"
    assert call["headers"]["Authorization"] == "Bearer k"
    assert call["data"]["model"] == DEFAULT_MODEL
    assert call["data"]["response_format"] == "json"
    name, wav_bytes, mime = call["files"]["file"]
    assert name == "audio.wav"
    assert wav_bytes.startswith(b"RIFF")
    assert mime == "audio/wav"


@pytest.mark.asyncio
async def test_base_mode_appends_documented_path_and_uses_declared_model(monkeypatch):
    _settings(monkeypatch)
    client = _FakeClient(resp=_FakeResp(payload={"text": "hello world"}))
    _patch_client(monkeypatch, client)
    provider = MiniMaxSttProvider()
    out = await provider.transcribe(
        _PCM_B64, sample_rate=16000, creds=_creds(model="asr-1.0")
    )
    assert out == "hello world"
    assert client.post_calls[0]["url"] == "https://api.minimaxi.com/v1/speech_to_text"
    assert client.post_calls[0]["data"]["model"] == "asr-1.0"


@pytest.mark.asyncio
async def test_short_text_returns_empty(monkeypatch):
    _settings(monkeypatch)
    client = _FakeClient(resp=_FakeResp(payload={"text": " 好 "}))
    _patch_client(monkeypatch, client)
    provider = MiniMaxSttProvider()
    assert await provider.transcribe(_PCM_B64, sample_rate=16000, creds=_creds()) == ""


@pytest.mark.asyncio
async def test_non_dict_payload_returns_empty(monkeypatch):
    _settings(monkeypatch)
    client = _FakeClient(resp=_FakeResp(payload="plain"))
    _patch_client(monkeypatch, client)
    provider = MiniMaxSttProvider()
    assert await provider.transcribe(_PCM_B64, sample_rate=16000, creds=_creds()) == ""


def _http_status_error(status=401, text="authorized error"):
    req = httpx.Request("POST", "https://api.minimaxi.com/v1/speech_to_text")
    resp = httpx.Response(status, text=text, request=req)
    return httpx.HTTPStatusError("err", request=req, response=resp)


@pytest.mark.asyncio
async def test_http_error_returns_empty(monkeypatch):
    _settings(monkeypatch)
    client = _FakeClient(post_exc=_http_status_error())
    _patch_client(monkeypatch, client)
    provider = MiniMaxSttProvider()
    assert await provider.transcribe(_PCM_B64, sample_rate=16000, creds=_creds()) == ""


@pytest.mark.asyncio
async def test_generic_error_returns_empty(monkeypatch):
    _settings(monkeypatch)
    client = _FakeClient(post_exc=RuntimeError("net down"))
    _patch_client(monkeypatch, client)
    provider = MiniMaxSttProvider()
    assert await provider.transcribe(_PCM_B64, sample_rate=16000, creds=_creds()) == ""


@pytest.mark.asyncio
async def test_default_request_omits_language_header(monkeypatch):
    """No language hint by default so MiniMax mixed-language recognition stays on."""
    _settings(monkeypatch)
    client = _FakeClient(resp=_FakeResp(payload={"text": "mixed 中 en"}))
    _patch_client(monkeypatch, client)
    provider = MiniMaxSttProvider()
    await provider.transcribe(_PCM_B64, sample_rate=16000, creds=_creds())
    headers = client.post_calls[0]["headers"]
    assert "language" not in headers
    assert headers["Authorization"] == "Bearer k"


@pytest.mark.asyncio
async def test_stt_request_extras_override_any_field_or_header(monkeypatch):
    """extras.stt_request deep-merges: add the language header and override response_format."""
    _settings(monkeypatch)
    client = _FakeClient(resp=_FakeResp(payload={"text": "hello"}))
    _patch_client(monkeypatch, client)
    creds = _creds(
        model="",
        extra={
            "stt_request": {
                "headers": {"language": "zh"},
                "fields": {"response_format": "verbose_json"},
            }
        },
    )
    provider = MiniMaxSttProvider()
    await provider.transcribe(_PCM_B64, sample_rate=16000, creds=creds)
    call = client.post_calls[0]
    assert call["headers"]["language"] == "zh"
    assert call["data"]["response_format"] == "verbose_json"
    # Descriptor default survives where the override is silent.
    assert call["data"]["model"] == DEFAULT_MODEL


def test_build_stt_request_creds_model_wins_over_descriptor():
    headers, fields = minimax_stt_mod.build_stt_request(_creds(model="asr-custom"))
    assert headers == {}
    assert fields["model"] == "asr-custom"


def test_build_stt_request_local_whisper_size_falls_back_to_descriptor():
    """build_stt_credentials fills generic whisper sizes ("base") when the entry has no
    model; they are not MiniMax ids, so the descriptor default (asr-1.0) must apply."""
    for size in ("base", "tiny", "small", "medium", "large-v3"):
        _, fields = minimax_stt_mod.build_stt_request(_creds(model=size))
        assert fields["model"] == DEFAULT_MODEL
