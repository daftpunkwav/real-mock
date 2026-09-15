"""Aliyun STT tests for src/realmock/platform/capabilities/voice/stt/aliyun.py.

Covers: AliyunProvider missing-creds/wav-failure/post-failure/success-status
branches including app-key fallback and result/error variants (HTTP faked).
Conventions: no real network/model downloads (all clients mocked).
"""

from __future__ import annotations

import base64
from unittest.mock import patch

import pytest

from realmock.platform.capabilities.voice.stt import aliyun as aliyun_mod
from realmock.platform.capabilities.voice.stt.aliyun import AliyunProvider
from realmock.platform.capabilities.voice.stt.base import SttCredentials


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


@pytest.mark.asyncio
async def test_aliyun_missing_creds():
    p = AliyunProvider()
    assert await p.transcribe(PCM, sample_rate=16000, creds=SttCredentials()) == ""
    assert await p.transcribe(PCM, sample_rate=16000, creds=SttCredentials(app_key="k")) == ""
    assert await p.transcribe(PCM, sample_rate=16000, creds=SttCredentials(api_key="t")) == ""


@pytest.mark.asyncio
async def test_aliyun_wav_failure(monkeypatch):
    monkeypatch.setattr(aliyun_mod, "make_pinned_async_client", lambda *a, **k: _FakeClient())
    with patch.object(aliyun_mod, "pcm_base64_to_wav_bytes", side_effect=RuntimeError("wav")):
        assert (
            await AliyunProvider().transcribe(
                PCM, sample_rate=16000, creds=SttCredentials(app_key="k", api_key="t")
            )
            == ""
        )


@pytest.mark.asyncio
async def test_aliyun_post_failure(monkeypatch):
    monkeypatch.setattr(
        aliyun_mod,
        "make_pinned_async_client",
        lambda *a, **k: _FakeClient(post_exc=RuntimeError("x")),
    )
    assert (
        await AliyunProvider().transcribe(
            PCM, sample_rate=16000, creds=SttCredentials(app_key="k", api_key="t")
        )
        == ""
    )


@pytest.mark.asyncio
async def test_aliyun_success_and_status_branches(monkeypatch):
    # app_id fallback for app_key.
    client = _FakeClient(post_resp=_FakeResp(payload={"status": 20000000, "result": " ni hao "}))
    monkeypatch.setattr(aliyun_mod, "make_pinned_async_client", lambda *a, **k: client)
    out = await AliyunProvider().transcribe(
        PCM, sample_rate=16000, creds=SttCredentials(app_id="mykey", api_key="tok")
    )
    assert out == "ni hao"
    assert "appkey=mykey" in client.post_calls[0]["url"]
    assert client.post_calls[0]["headers"]["X-NLS-Token"] == "tok"

    # status 0 success.
    client2 = _FakeClient(post_resp=_FakeResp(payload={"status": 0, "result": "ok"}))
    monkeypatch.setattr(aliyun_mod, "make_pinned_async_client", lambda *a, **k: client2)
    assert (
        await AliyunProvider().transcribe(
            PCM, sample_rate=16000, creds=SttCredentials(app_key="k", api_key="t")
        )
        == "ok"
    )

    # status None with result.
    client3 = _FakeClient(post_resp=_FakeResp(payload={"result": "r"}))
    monkeypatch.setattr(aliyun_mod, "make_pinned_async_client", lambda *a, **k: client3)
    assert (
        await AliyunProvider().transcribe(
            PCM, sample_rate=16000, creds=SttCredentials(app_key="k", api_key="t")
        )
        == "r"
    )

    # Error status without result -> "".
    client4 = _FakeClient(post_resp=_FakeResp(payload={"status": 500, "message": "fail"}))
    monkeypatch.setattr(aliyun_mod, "make_pinned_async_client", lambda *a, **k: client4)
    assert (
        await AliyunProvider().transcribe(
            PCM, sample_rate=16000, creds=SttCredentials(app_key="k", api_key="t")
        )
        == ""
    )

    # Error status code but result present -> returns result (edge of fallback semantics).
    client5 = _FakeClient(post_resp=_FakeResp(payload={"status": 500, "result": "kept"}))
    monkeypatch.setattr(aliyun_mod, "make_pinned_async_client", lambda *a, **k: client5)
    assert (
        await AliyunProvider().transcribe(
            PCM, sample_rate=16000, creds=SttCredentials(app_key="k", api_key="t")
        )
        == "kept"
    )

    # Empty result -> "".
    client6 = _FakeClient(post_resp=_FakeResp(payload={"status": 20000000}))
    monkeypatch.setattr(aliyun_mod, "make_pinned_async_client", lambda *a, **k: client6)
    assert (
        await AliyunProvider().transcribe(
            PCM, sample_rate=16000, creds=SttCredentials(app_key="k", api_key="t")
        )
        == ""
    )
