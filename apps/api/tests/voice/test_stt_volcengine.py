"""Volcengine STT tests for src/realmock/platform/capabilities/voice/stt/volcengine.py.

Covers: VolcengineProvider missing-creds/cred-fallbacks/wav-post-failure/
result-variants/custom-resource-model branches (HTTP client faked).
Conventions: no real network/model downloads (all clients mocked).
"""

from __future__ import annotations

import base64
from unittest.mock import patch

import pytest

from realmock.platform.capabilities.voice.stt import volcengine as volc_mod
from realmock.platform.capabilities.voice.stt.base import SttCredentials
from realmock.platform.capabilities.voice.stt.volcengine import VolcengineProvider


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
async def test_volc_missing_creds():
    p = VolcengineProvider()
    assert await p.transcribe(PCM, sample_rate=16000, creds=SttCredentials()) == ""
    assert await p.transcribe(PCM, sample_rate=16000, creds=SttCredentials(app_key="k")) == ""


@pytest.mark.asyncio
async def test_volc_cred_fallbacks(monkeypatch):
    client = _FakeClient(post_resp=_FakeResp(payload={"result": {"text": "ok"}}))
    monkeypatch.setattr(volc_mod, "make_pinned_async_client", lambda *a, **k: client)
    # app_id as app_key, api_key as access_key.
    out = await VolcengineProvider().transcribe(
        PCM, sample_rate=16000, creds=SttCredentials(app_id="ak", api_key="sk")
    )
    assert out == "ok"
    assert client.post_calls[0]["headers"]["X-Api-App-Key"] == "ak"
    assert client.post_calls[0]["headers"]["X-Api-Access-Key"] == "sk"
    assert client.post_calls[0]["headers"]["X-Api-Resource-Id"] == "volc.bigasr.auc_turbo"


@pytest.mark.asyncio
async def test_volc_wav_and_post_failure(monkeypatch):
    monkeypatch.setattr(volc_mod, "make_pinned_async_client", lambda *a, **k: _FakeClient())
    with patch.object(volc_mod, "pcm_base64_to_wav_bytes", side_effect=RuntimeError("wav")):
        assert (
            await VolcengineProvider().transcribe(
                PCM, sample_rate=16000, creds=SttCredentials(app_key="k", access_key="s")
            )
            == ""
        )
    monkeypatch.setattr(
        volc_mod,
        "make_pinned_async_client",
        lambda *a, **k: _FakeClient(post_exc=RuntimeError("x")),
    )
    assert (
        await VolcengineProvider().transcribe(
            PCM, sample_rate=16000, creds=SttCredentials(app_key="k", access_key="s")
        )
        == ""
    )


@pytest.mark.asyncio
async def test_volc_result_variants(monkeypatch):
    cases = [
        ({"result": {"text": " direct "}}, "direct"),
        ({"result": {"utterances": [{"text": "a"}, {"text": "b"}, "x"]}}, "ab"),
        ({"result": {"utterances": []}}, ""),
        ({"result": "plain str "}, "plain str"),
        ({"data": {"text": "via data"}}, "via data"),
        ({"result": 123}, ""),
        ({"other": 1}, ""),
    ]
    for payload, expected in cases:
        client = _FakeClient(post_resp=_FakeResp(payload=payload))
        monkeypatch.setattr(volc_mod, "make_pinned_async_client", lambda *a, **k: client)
        out = await VolcengineProvider().transcribe(
            PCM, sample_rate=16000, creds=SttCredentials(app_key="k", access_key="s")
        )
        assert out == expected


@pytest.mark.asyncio
async def test_volc_custom_resource_and_model(monkeypatch):
    client = _FakeClient(post_resp=_FakeResp(payload={"result": {"text": "ok"}}))
    monkeypatch.setattr(volc_mod, "make_pinned_async_client", lambda *a, **k: client)
    await VolcengineProvider().transcribe(
        PCM,
        sample_rate=16000,
        creds=SttCredentials(app_key="k", access_key="s", resource_id="custom", model="m1"),
    )
    assert client.post_calls[0]["headers"]["X-Api-Resource-Id"] == "custom"
    assert client.post_calls[0]["json"]["request"]["model_name"] == "m1"
