"""Generic JSON-template adapter tests (STT + TTS).

These transports let users adapt vendors without a dedicated adapter by authoring a
request descriptor in model-entry extras (``stt_adapter`` / ``tts_adapter``).
Covers: placeholder substitution, multipart vs JSON audio delivery, dotted response
paths, hex/base64 audio decoding, and STT router dispatch priority.
"""

from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest

from realmock.platform.capabilities.voice.stt.base import SttCredentials
from realmock.platform.capabilities.voice.stt.providers import json_template as stt_mod
from realmock.platform.capabilities.voice.stt.providers.json_template import (
    JsonTemplateSttProvider,
    resolve_stt_adapter,
)
from realmock.platform.capabilities.voice.stt import router as stt_router
from realmock.platform.capabilities.voice.tts import TtsCredentials
from realmock.platform.capabilities.voice.tts.providers import json_template as tts_mod
from realmock.platform.capabilities.voice.tts.providers.json_template import (
    synthesize_json_template_to_base64,
)

_PCM_B64 = base64.b64encode(b"\x00\x00" * 16000).decode("ascii")


def _stt_settings(monkeypatch):
    monkeypatch.setattr(
        stt_mod, "get_settings", lambda: SimpleNamespace(allow_local_llm=False, is_prod=False)
    )


def _tts_settings(monkeypatch):
    monkeypatch.setattr(
        tts_mod, "get_settings", lambda: SimpleNamespace(allow_local_llm=False, is_prod=False)
    )


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def request(self, method, url, headers=None, data=None, files=None, content=None):
        self.calls.append(
            {"method": method, "url": url, "headers": headers, "data": data,
             "files": files, "content": content}
        )
        return _FakeResp(self._payload)

    async def post(self, url, headers=None, data=None, files=None, content=None):
        return await self.request("POST", url, headers=headers, data=data, files=files, content=content)


def _stt_adapter() -> dict:
    return {
        "url": "https://vendor.example/v1/asr?k={{api_key}}",
        "headers": {"X-Vendor": "{{model}}"},
        "fields": {"model": "{{model}}", "lang": "zh"},
        "text_path": "result.text",
    }


@pytest.mark.asyncio
async def test_stt_template_substitutes_and_reads_dotted_path(monkeypatch):
    _stt_settings(monkeypatch)
    client = _FakeClient({"result": {"text": "你好 世界"}})
    monkeypatch.setattr(stt_mod, "make_pinned_async_client", lambda *a, **k: client)
    creds = SttCredentials(
        provider="custom", api_key="k", model="asr-x",
        extra={"stt_adapter": _stt_adapter()},
    )
    out = await JsonTemplateSttProvider().transcribe(_PCM_B64, sample_rate=16000, creds=creds)
    assert out == "你好 世界"
    call = client.calls[0]
    assert "k" in call["url"]
    assert call["headers"]["Authorization"] == "Bearer k"
    assert call["headers"]["X-Vendor"] == "asr-x"
    assert call["data"]["model"] == "asr-x"
    name, wav, mime = call["files"]["file"]
    assert name == "audio.wav" and wav.startswith(b"RIFF") and mime == "audio/wav"


@pytest.mark.asyncio
async def test_stt_template_json_body_carries_audio_base64(monkeypatch):
    _stt_settings(monkeypatch)
    client = _FakeClient({"text": "hi"})
    monkeypatch.setattr(stt_mod, "make_pinned_async_client", lambda *a, **k: client)
    creds = SttCredentials(
        provider="custom", api_key="k", model="m",
        extra={"stt_adapter": {"url": "https://v.example/asr", "json_body": {"a": "{{audio_base64}}"}}},
    )
    assert await JsonTemplateSttProvider().transcribe(_PCM_B64, sample_rate=16000, creds=creds) == "hi"
    assert b"audio/wav" not in (client.calls[0]["content"] or b"")


def test_resolve_stt_adapter_requires_url():
    assert resolve_stt_adapter(SttCredentials(extra={})) is None
    assert resolve_stt_adapter(SttCredentials(extra={"stt_adapter": {"url": ""}})) is None
    assert resolve_stt_adapter(SttCredentials(extra={"stt_adapter": {"url": "https://x"}})) is not None


@pytest.mark.asyncio
async def test_stt_router_dispatches_to_json_template(monkeypatch):
    """The user adapter wins over the openai_chat protocol guess."""
    seen = {}

    async def _fake_transcribe(self, pcm_b64, *, sample_rate, creds):
        seen["called"] = True
        return " routed "

    monkeypatch.setattr(JsonTemplateSttProvider, "transcribe", _fake_transcribe)
    creds = SttCredentials(
        provider="my-vendor", protocol="openai_chat", api_base="https://v.example",
        api_key="k", model="m", extra={"stt_adapter": {"url": "https://v.example/asr"}},
    )
    result = await stt_router.transcribe_with_handler(_PCM_B64, sample_rate=16000, creds=creds)
    assert seen["called"] is True
    assert result.provider == "my-vendor"
    assert result.fallback is False


@pytest.mark.asyncio
async def test_tts_template_substitutes_text_and_decodes_hex(monkeypatch):
    _tts_settings(monkeypatch)
    raw = b"fake-mp3-bytes"
    client = _FakeClient({"data": {"audio": raw.hex()}})
    monkeypatch.setattr(tts_mod, "make_pinned_async_client", lambda *a, **k: client)
    creds = TtsCredentials(
        handler="custom", api_key="k", model="tts-x", voice="main",
        extra={"tts_adapter": {
            "url": "https://v.example/tts",
            "body": {"model": "{{model}}", "text": "{{text}}", "voice": "{{voice}}"},
            "audio_path": "data.audio",
            "audio_encoding": "hex",
        }},
    )
    out = await synthesize_json_template_to_base64("你好", creds=creds)
    assert base64.b64decode(out) == raw
    import json

    body = json.loads(client.calls[0]["content"])
    assert body == {"model": "tts-x", "text": "你好", "voice": "main"}


@pytest.mark.asyncio
async def test_tts_template_base64_audio(monkeypatch):
    _tts_settings(monkeypatch)
    raw = b"audio-bytes"
    client = _FakeClient({"data": {"audio": base64.b64encode(raw).decode("ascii")}})
    monkeypatch.setattr(tts_mod, "make_pinned_async_client", lambda *a, **k: client)
    creds = TtsCredentials(
        handler="custom", api_key="k",
        extra={"tts_adapter": {"url": "https://v.example/tts", "audio_encoding": "base64"}},
    )
    out = await synthesize_json_template_to_base64("hi", creds=creds)
    assert base64.b64decode(out) == raw
