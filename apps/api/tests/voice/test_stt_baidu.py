"""Baidu STT tests for src/realmock/platform/capabilities/voice/stt/baidu.py.

Covers: BaiduProvider missing-creds/token-exception/empty-token/wav-failure/
post-failure/success-body/error-empty branches (HTTP client faked).
Conventions: no real network/model downloads (all clients mocked).
"""

from __future__ import annotations

import base64
from unittest.mock import patch

import pytest

from realmock.platform.capabilities.voice.stt import baidu as baidu_mod
from realmock.platform.capabilities.voice.stt.baidu import BaiduProvider
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
async def test_baidu_missing_creds():
    p = BaiduProvider()
    assert await p.transcribe(PCM, sample_rate=16000, creds=SttCredentials()) == ""
    assert await p.transcribe(PCM, sample_rate=16000, creds=SttCredentials(api_key="k")) == ""
    assert (
        await p.transcribe(
            PCM, sample_rate=16000, creds=SttCredentials(api_key="k", api_secret="  ")
        )
        == ""
    )


@pytest.mark.asyncio
async def test_baidu_token_exception(monkeypatch):
    client = _FakeClient(get_exc=RuntimeError("net"))
    monkeypatch.setattr(baidu_mod, "make_pinned_async_client", lambda *a, **k: client)
    p = BaiduProvider()
    assert (
        await p.transcribe(
            PCM, sample_rate=16000, creds=SttCredentials(api_key="k", api_secret="s")
        )
        == ""
    )


@pytest.mark.asyncio
async def test_baidu_empty_token(monkeypatch):
    client = _FakeClient(get_resp=_FakeResp(payload={"access_token": ""}))
    monkeypatch.setattr(baidu_mod, "make_pinned_async_client", lambda *a, **k: client)
    p = BaiduProvider()
    assert (
        await p.transcribe(
            PCM, sample_rate=16000, creds=SttCredentials(api_key="k", api_secret="s")
        )
        == ""
    )


@pytest.mark.asyncio
async def test_baidu_wav_failure(monkeypatch):
    token_client = _FakeClient(get_resp=_FakeResp(payload={"access_token": "tok"}))

    def factory(url, **kw):
        return token_client

    monkeypatch.setattr(baidu_mod, "make_pinned_async_client", factory)
    with patch.object(baidu_mod, "pcm_base64_to_wav_bytes", side_effect=RuntimeError("wav")):
        p = BaiduProvider()
        assert (
            await p.transcribe(
                PCM, sample_rate=16000, creds=SttCredentials(api_key="k", api_secret="s")
            )
            == ""
        )


@pytest.mark.asyncio
async def test_baidu_post_failure(monkeypatch):
    calls = []

    def factory(url, **kw):
        if "oauth" in url:
            return _FakeClient(get_resp=_FakeResp(payload={"access_token": "tok"}))
        c = _FakeClient(post_exc=RuntimeError("down"))
        calls.append(c)
        return c

    monkeypatch.setattr(baidu_mod, "make_pinned_async_client", factory)
    p = BaiduProvider()
    assert (
        await p.transcribe(
            PCM, sample_rate=16000, creds=SttCredentials(api_key="k", api_secret="s")
        )
        == ""
    )


@pytest.mark.asyncio
async def test_baidu_success_and_body(monkeypatch):
    captured = {}

    def factory(url, **kw):
        if "oauth" in url:
            return _FakeClient(get_resp=_FakeResp(payload={"access_token": "tok123"}))
        c = _FakeClient(post_resp=_FakeResp(payload={"err_no": 0, "result": [" hello baidu "]}))
        captured["client"] = c
        return c

    monkeypatch.setattr(baidu_mod, "make_pinned_async_client", factory)
    p = BaiduProvider()
    out = await p.transcribe(
        PCM, sample_rate=8000, creds=SttCredentials(api_key="k", api_secret="s")
    )
    assert out == "hello baidu"
    body = captured["client"].post_calls[0]["json"]
    assert body["token"] == "tok123"
    assert body["rate"] == 8000
    assert body["format"] == "wav"


@pytest.mark.asyncio
async def test_baidu_error_and_empty_results(monkeypatch):
    for payload, _ in [
        ({"err_no": 3300, "err_msg": "bad"}, None),
        ({"err_no": 0, "result": []}, None),
        ({"err_no": None, "result": [" ok "]}, None),
    ]:

        def factory(url, _p=payload, **kw):
            if "oauth" in url:
                return _FakeClient(get_resp=_FakeResp(payload={"access_token": "t"}))
            return _FakeClient(post_resp=_FakeResp(payload=_p))

        monkeypatch.setattr(baidu_mod, "make_pinned_async_client", factory)
        p = BaiduProvider()
        out = await p.transcribe(
            PCM, sample_rate=16000, creds=SttCredentials(api_key="k", api_secret="s")
        )
        if payload.get("err_no") not in (0, None):
            assert out == ""
        elif not payload.get("result"):
            assert out == ""
        else:
            assert out == "ok"
