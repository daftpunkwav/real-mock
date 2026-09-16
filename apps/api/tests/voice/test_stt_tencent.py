"""Tencent STT tests for src/realmock/platform/capabilities/voice/stt/tencent.py.

Covers: _sign_tc3 shape, TencentProvider missing-creds/wav-failure/success-digit/
non-digit/error/post-failure/empty branches (HTTP client faked).
Conventions: no real network/model downloads (all clients mocked).
"""

from __future__ import annotations

import base64
from unittest.mock import patch

import pytest

from realmock.platform.capabilities.voice.stt.providers import tencent as tencent_mod
from realmock.platform.capabilities.voice.stt.base import SttCredentials
from realmock.platform.capabilities.voice.stt.providers.tencent import TencentProvider, _sign_tc3


class _FakeResp:
    def __init__(self, payload=None, raise_exc=None):
        self._payload = payload
        self._raise_exc = raise_exc

    def raise_for_status(self):
        if self._raise_exc is not None:
            raise self._raise_exc

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _FakeClient:
    def __init__(self, get_resp=None, post_resp=None, get_exc=None, post_exc=None):
        self._get_resp = get_resp
        self._post_resp = post_resp
        self._get_exc = get_exc
        self._post_exc = post_exc
        self.get_calls = []
        self.post_calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None):
        self.get_calls.append({"url": url, "params": params})
        if self._get_exc is not None:
            raise self._get_exc
        return self._get_resp

    async def post(self, url, headers=None, json=None, content=None):
        self.post_calls.append({"url": url, "headers": headers, "json": json, "content": content})
        if self._post_exc is not None:
            raise self._post_exc
        return self._post_resp


PCM = base64.b64encode(b"\x00\x01" * 500).decode("ascii")


def test_sign_tc3_shape():
    headers = _sign_tc3(secret_id="id", secret_key="key", payload="{}", timestamp=1700000000)
    assert headers["Authorization"].startswith("TC3-HMAC-SHA256 ")
    assert "Credential=id/" in headers["Authorization"]
    assert headers["Host"] == "asr.tencentcloudapi.com"
    assert headers["X-TC-Action"] == "SentenceRecognition"
    assert headers["X-TC-Timestamp"] == "1700000000"


@pytest.mark.asyncio
async def test_tencent_missing_creds():
    p = TencentProvider()
    assert await p.transcribe(PCM, sample_rate=16000, creds=SttCredentials()) == ""
    assert await p.transcribe(PCM, sample_rate=16000, creds=SttCredentials(api_key="id")) == ""


@pytest.mark.asyncio
async def test_tencent_wav_failure(monkeypatch):
    monkeypatch.setattr(tencent_mod, "make_pinned_async_client", lambda *a, **k: _FakeClient())
    with patch.object(tencent_mod, "pcm_base64_to_wav_bytes", side_effect=RuntimeError("wav")):
        assert (
            await TencentProvider().transcribe(
                PCM, sample_rate=16000, creds=SttCredentials(api_key="id", api_secret="key")
            )
            == ""
        )


@pytest.mark.asyncio
async def test_tencent_success_digit_app_id(monkeypatch):
    client = _FakeClient(post_resp=_FakeResp(payload={"Response": {"Result": " tengxun ok "}}))
    monkeypatch.setattr(tencent_mod, "make_pinned_async_client", lambda *a, **k: client)
    out = await TencentProvider().transcribe(
        PCM,
        sample_rate=16000,
        creds=SttCredentials(app_id="12345", api_key="id", api_secret="key"),
    )
    assert out == "tengxun ok"
    # Body is JSON string payload; verify via content arg.
    assert client.post_calls[0]["content"] is not None


@pytest.mark.asyncio
async def test_tencent_non_digit_app_id_and_error(monkeypatch):
    client = _FakeClient(post_resp=_FakeResp(payload={"Response": {"Result": "hi"}}))
    monkeypatch.setattr(tencent_mod, "make_pinned_async_client", lambda *a, **k: client)
    out = await TencentProvider().transcribe(
        PCM,
        sample_rate=16000,
        creds=SttCredentials(app_id="abc", api_key="id", api_secret="key"),
    )
    assert out == "hi"

    client2 = _FakeClient(
        post_resp=_FakeResp(payload={"Response": {"Error": {"Code": "E", "Message": "m"}}})
    )
    monkeypatch.setattr(tencent_mod, "make_pinned_async_client", lambda *a, **k: client2)
    assert (
        await TencentProvider().transcribe(
            PCM, sample_rate=16000, creds=SttCredentials(api_key="id", api_secret="key")
        )
        == ""
    )


@pytest.mark.asyncio
async def test_tencent_post_failure_and_empty(monkeypatch):
    monkeypatch.setattr(
        tencent_mod,
        "make_pinned_async_client",
        lambda *a, **k: _FakeClient(post_exc=RuntimeError("x")),
    )
    assert (
        await TencentProvider().transcribe(
            PCM, sample_rate=16000, creds=SttCredentials(api_key="id", api_secret="key")
        )
        == ""
    )
    client = _FakeClient(post_resp=_FakeResp(payload={"Response": {}}))
    monkeypatch.setattr(tencent_mod, "make_pinned_async_client", lambda *a, **k: client)
    assert (
        await TencentProvider().transcribe(
            PCM, sample_rate=16000, creds=SttCredentials(api_key="id", api_secret="key")
        )
        == ""
    )
