"""OpenAI-compat STT tests for src/realmock/platform/capabilities/voice/stt/openai_compat.py.

Covers: _decode_audio variants/wav-failure branches, MimoAudioProvider
missing-creds/bad-audio/success-str/success-list/empty/HTTP/generic branches,
transcribe_pcm_cloud/OpenAICompatProvider delegation branches (HTTP faked).
Conventions: no real network/model downloads (all clients mocked).
"""

from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from realmock.platform.capabilities.voice.stt import cloud as cloud_mod
from realmock.platform.capabilities.voice.stt import openai_compat as compat_mod
from realmock.platform.capabilities.voice.stt.base import SttCredentials

LONG_PCM = base64.b64encode(b"\x00\x01" * 6000).decode("ascii")
SHORT_PCM = base64.b64encode(b"\x00\x01" * 100).decode("ascii")


def _settings(monkeypatch, module):
    monkeypatch.setattr(
        module, "get_settings", lambda: SimpleNamespace(allow_local_llm=False, is_prod=False)
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

    async def post(self, url, headers=None, data=None, json=None, files=None):
        self.calls.append(
            {"url": url, "headers": headers, "data": data, "json": json, "files": files}
        )
        if self._post_exc is not None:
            raise self._post_exc
        return self._resp


def _http_status_error():
    req = httpx.Request("POST", "https://x/audio/transcriptions")
    resp = httpx.Response(500, text="stt boom", request=req)
    return httpx.HTTPStatusError("e", request=req, response=resp)


def _wav_b64():
    from realmock.platform.capabilities.voice.stt.whisper import pcm_base64_to_wav_bytes

    wav = pcm_base64_to_wav_bytes(SHORT_PCM, 16000)
    return base64.b64encode(wav).decode("ascii")


def test_decode_audio_variants():
    # Single char is invalid base64 padding -> decode failure -> b"".
    assert compat_mod._decode_audio("a") == b""
    wav_b64 = _wav_b64()
    assert compat_mod._decode_audio(wav_b64)[:4] == b"RIFF"
    # PCM without RIFF gets wrapped to wav.
    assert compat_mod._decode_audio(SHORT_PCM)[:4] == b"RIFF"


def test_decode_audio_wav_failure(monkeypatch):
    with patch(
        "realmock.platform.capabilities.voice.stt.cloud.pcm_base64_to_wav_bytes",
        side_effect=RuntimeError("wav"),
    ):
        assert compat_mod._decode_audio(SHORT_PCM) == b""


@pytest.mark.asyncio
async def test_mimo_missing_creds_and_bad_audio():
    p = compat_mod.MimoAudioProvider()
    assert await p.transcribe(LONG_PCM, sample_rate=16000, creds=SttCredentials(api_key="")) == ""
    assert await p.transcribe(LONG_PCM, sample_rate=16000, creds=SttCredentials(api_base="")) == ""
    assert (
        await p.transcribe(
            "a", sample_rate=16000, creds=SttCredentials(api_key="k", api_base="https://x")
        )
        == ""
    )


@pytest.mark.asyncio
async def test_mimo_success_str_content(monkeypatch):
    _settings(monkeypatch, compat_mod)
    wav_b64 = _wav_b64()
    client = _FakeClient(
        resp=_FakeResp(payload={"choices": [{"message": {"content": "  hi there  "}}]})
    )
    monkeypatch.setattr(compat_mod, "make_pinned_async_client", lambda *a, **k: client)
    p = compat_mod.MimoAudioProvider()
    out = await p.transcribe(
        wav_b64, sample_rate=16000, creds=SttCredentials(api_key="k", api_base="https://x/")
    )
    assert out == "hi there"
    call = client.calls[0]
    assert call["url"] == "https://x/chat/completions"
    assert call["json"]["model"] == "mimo-v2.5-asr"
    # data URI wraps wav bytes.
    data_uri = call["json"]["messages"][0]["content"][0]["input_audio"]["data"]
    assert data_uri.startswith("data:audio/wav;base64,")


@pytest.mark.asyncio
async def test_mimo_success_list_content(monkeypatch):
    _settings(monkeypatch, compat_mod)
    client = _FakeClient(
        resp=_FakeResp(
            payload={"choices": [{"message": {"content": [{"text": "he"}, {"text": "llo"}, "x"]}}]}
        )
    )
    monkeypatch.setattr(compat_mod, "make_pinned_async_client", lambda *a, **k: client)
    p = compat_mod.MimoAudioProvider()
    out = await p.transcribe(
        _wav_b64(), sample_rate=16000, creds=SttCredentials(api_key="k", api_base="https://x")
    )
    assert out == "hello"


@pytest.mark.asyncio
async def test_mimo_empty_choices_and_none_content(monkeypatch):
    _settings(monkeypatch, compat_mod)
    for payload in [
        {},
        {"choices": []},
        {"choices": [{"message": {}}]},
        {"choices": [{"message": {"content": None}}]},
    ]:
        client = _FakeClient(resp=_FakeResp(payload=payload))
        monkeypatch.setattr(compat_mod, "make_pinned_async_client", lambda *a, **k: client)
        p = compat_mod.MimoAudioProvider()
        assert (
            await p.transcribe(
                _wav_b64(),
                sample_rate=16000,
                creds=SttCredentials(api_key="k", api_base="https://x"),
            )
            == ""
        )


@pytest.mark.asyncio
async def test_mimo_http_and_generic_errors(monkeypatch):
    _settings(monkeypatch, compat_mod)
    req = httpx.Request("POST", "https://x/chat/completions")
    resp = httpx.Response(500, text="boom", request=req)
    http_exc = httpx.HTTPStatusError("e", request=req, response=resp)
    client = _FakeClient(post_exc=http_exc)
    monkeypatch.setattr(compat_mod, "make_pinned_async_client", lambda *a, **k: client)
    p = compat_mod.MimoAudioProvider()
    assert (
        await p.transcribe(
            _wav_b64(), sample_rate=16000, creds=SttCredentials(api_key="k", api_base="https://x")
        )
        == ""
    )
    client2 = _FakeClient(post_exc=RuntimeError("down"))
    monkeypatch.setattr(compat_mod, "make_pinned_async_client", lambda *a, **k: client2)
    assert (
        await p.transcribe(
            _wav_b64(), sample_rate=16000, creds=SttCredentials(api_key="k", api_base="https://x")
        )
        == ""
    )


@pytest.mark.asyncio
async def test_compat_transcribe_pcm_cloud_delegates():
    with patch.object(cloud_mod, "transcribe_pcm_cloud", new=AsyncMock(return_value="CLOUD")) as m:
        out = await compat_mod.transcribe_pcm_cloud("AAA", model="m", api_base="b", api_key="k")
    assert out == "CLOUD"
    assert m.await_args.kwargs["model"] == "m"


@pytest.mark.asyncio
async def test_openai_compat_provider_delegates():
    with patch.object(compat_mod, "transcribe_pcm_cloud", new=AsyncMock(return_value="OC")) as m:
        p = compat_mod.OpenAICompatProvider()
        out = await p.transcribe(
            "AAA", sample_rate=16000, creds=SttCredentials(model="", api_base="b", api_key="k")
        )
    assert out == "OC"
    assert m.await_args.kwargs["model"] == "FunAudioLLM/SenseVoiceSmall"
