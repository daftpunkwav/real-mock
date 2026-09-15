"""Cloud STT tests for src/realmock/platform/capabilities/voice/stt/cloud.py.

Covers: is_local_stt_model/resolve_cloud_stt_model branches, transcribe_pcm_cloud
missing-creds/bad-base64/short-audio/wav-failure/success/model-resolve/language/
str-payload/short-text/HTTP/generic/body-unreadable branches (HTTP client faked).
Conventions: no real network/model downloads (all clients mocked).
"""

from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from realmock.platform.capabilities.voice.stt import cloud as cloud_mod
from realmock.platform.capabilities.voice.stt.cloud import (
    is_local_stt_model,
    resolve_cloud_stt_model,
    transcribe_pcm_cloud,
)

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


def test_is_local_and_resolve():
    assert is_local_stt_model("base")
    assert is_local_stt_model(" BASE ")
    assert is_local_stt_model("tiny")
    assert not is_local_stt_model("whisper-1")
    assert not is_local_stt_model("")
    assert resolve_cloud_stt_model("") == "whisper-1"
    assert resolve_cloud_stt_model("base") == "whisper-1"
    assert resolve_cloud_stt_model("whisper-1") == "whisper-1"
    assert resolve_cloud_stt_model("gpt-4o-mini-transcribe") == "gpt-4o-mini-transcribe"


@pytest.mark.asyncio
async def test_cloud_missing_creds():
    assert await transcribe_pcm_cloud(LONG_PCM, api_key="", api_base="https://x") == ""
    assert await transcribe_pcm_cloud(LONG_PCM, api_key="k", api_base="") == ""
    assert await transcribe_pcm_cloud(LONG_PCM, api_key="  ", api_base="  ") == ""


@pytest.mark.asyncio
async def test_cloud_bad_base64_and_short_audio():
    assert await transcribe_pcm_cloud("!!!not-b64", api_key="k", api_base="https://x") == ""
    assert await transcribe_pcm_cloud(SHORT_PCM, api_key="k", api_base="https://x") == ""


@pytest.mark.asyncio
async def test_cloud_wav_convert_failure(monkeypatch):
    _settings(monkeypatch, cloud_mod)
    with patch.object(cloud_mod, "pcm_base64_to_wav_bytes", side_effect=RuntimeError("wav")):
        assert await transcribe_pcm_cloud(LONG_PCM, api_key="k", api_base="https://x") == ""


@pytest.mark.asyncio
async def test_cloud_success_dict_payload(monkeypatch):
    _settings(monkeypatch, cloud_mod)
    client = _FakeClient(resp=_FakeResp(payload={"text": "  hello world  "}))
    monkeypatch.setattr(cloud_mod, "make_pinned_async_client", lambda *a, **k: client)
    out = await transcribe_pcm_cloud(LONG_PCM, api_key="k", api_base="https://x/")
    assert out == "hello world"
    call = client.calls[0]
    assert call["url"] == "https://x/audio/transcriptions"
    assert call["data"]["model"] == "whisper-1"
    assert call["data"]["language"] == "zh"
    assert call["headers"]["Authorization"] == "Bearer k"
    assert "file" in call["files"]


@pytest.mark.asyncio
async def test_cloud_model_resolve_and_language_override(monkeypatch):
    _settings(monkeypatch, cloud_mod)
    client = _FakeClient(resp=_FakeResp(payload={"text": "ok text"}))
    monkeypatch.setattr(cloud_mod, "make_pinned_async_client", lambda *a, **k: client)
    out = await transcribe_pcm_cloud(
        LONG_PCM, api_key="k", api_base="https://x", model="base", language="en"
    )
    assert out == "ok text"
    assert client.calls[0]["data"]["model"] == "whisper-1"
    assert client.calls[0]["data"]["language"] == "en"


@pytest.mark.asyncio
async def test_cloud_str_payload(monkeypatch):
    _settings(monkeypatch, cloud_mod)
    client = _FakeClient(resp=_FakeResp(payload=" spoken text "))
    monkeypatch.setattr(cloud_mod, "make_pinned_async_client", lambda *a, **k: client)
    assert await transcribe_pcm_cloud(LONG_PCM, api_key="k", api_base="https://x") == "spoken text"


@pytest.mark.asyncio
async def test_cloud_short_text_filtered(monkeypatch):
    _settings(monkeypatch, cloud_mod)
    for payload in [{"text": "a"}, {"text": "  "}, {"text": ""}, "x", {"no": "text"}]:
        client = _FakeClient(resp=_FakeResp(payload=payload))
        monkeypatch.setattr(cloud_mod, "make_pinned_async_client", lambda *a, **k: client)
        assert await transcribe_pcm_cloud(LONG_PCM, api_key="k", api_base="https://x") == ""


@pytest.mark.asyncio
async def test_cloud_http_and_generic_errors(monkeypatch):
    _settings(monkeypatch, cloud_mod)
    client = _FakeClient(post_exc=_http_status_error())
    monkeypatch.setattr(cloud_mod, "make_pinned_async_client", lambda *a, **k: client)
    assert await transcribe_pcm_cloud(LONG_PCM, api_key="k", api_base="https://x") == ""
    client2 = _FakeClient(post_exc=RuntimeError("down"))
    monkeypatch.setattr(cloud_mod, "make_pinned_async_client", lambda *a, **k: client2)
    assert await transcribe_pcm_cloud(LONG_PCM, api_key="k", api_base="https://x") == ""


@pytest.mark.asyncio
async def test_cloud_http_error_body_unreadable(monkeypatch):
    _settings(monkeypatch, cloud_mod)

    class _BadResp:
        status_code = 500

        @property
        def text(self):
            raise RuntimeError("no body")

    req = httpx.Request("POST", "https://x/audio/transcriptions")
    exc = httpx.HTTPStatusError("e", request=req, response=_BadResp())  # type: ignore[arg-type]
    client = _FakeClient(post_exc=exc)
    monkeypatch.setattr(cloud_mod, "make_pinned_async_client", lambda *a, **k: client)
    assert await transcribe_pcm_cloud(LONG_PCM, api_key="k", api_base="https://x") == ""
