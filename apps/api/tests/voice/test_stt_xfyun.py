"""Xfyun STT tests for src/realmock/platform/capabilities/voice/stt/xfyun.py.

Covers: _auth_url shape, XfyunProvider missing-creds/bad-audio/websockets-missing/
single-frame/multi-frame/code-error/empty/exception branches (websockets faked).
Conventions: no real network/model downloads (all clients mocked).
"""

from __future__ import annotations

import base64
import json
import sys
import types

import pytest
from unittest.mock import patch

from realmock.platform.capabilities.voice.stt.base import SttCredentials
from realmock.platform.capabilities.voice.stt.providers.xfyun import XfyunProvider, _auth_url


PCM = base64.b64encode(b"\x00\x01" * 500).decode("ascii")
LONG_PCM = base64.b64encode(b"\x00\x01" * 6000).decode("ascii")
SHORT_PCM = base64.b64encode(b"\x00\x01" * 100).decode("ascii")

class _FakeWS:
    def __init__(self, messages, send_exc=None):
        self._messages = list(messages)
        self._send_exc = send_exc
        self.sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def send(self, data):
        self.sent.append(data)
        if self._send_exc is not None:
            raise self._send_exc

    async def recv(self):
        if not self._messages:
            raise RuntimeError("no more messages")
        item = self._messages.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _install_ws(monkeypatch, ws):
    mod = types.ModuleType("websockets")
    captured = {}

    def _connect(url, **kw):
        captured["url"] = url
        captured["kw"] = kw
        return ws

    mod.connect = _connect
    monkeypatch.setitem(sys.modules, "websockets", mod)
    return captured


def _msg(code=0, words=None, status=2):
    ws_list = []
    if words:
        ws_list = [{"cw": [{"w": w} for w in words]}]
    return json.dumps(
        {"code": code, "message": "ok", "data": {"status": status, "result": {"ws": ws_list}}}
    )


def test_auth_url_shape():
    url = _auth_url(api_key="k", api_secret="s")
    assert url.startswith("https://iat-api.xfyun.cn/v2/iat?")
    assert "authorization=" in url
    assert "date=" in url
    assert "host=" in url
    other = _auth_url(api_key="k", api_secret="other")
    assert other != url


@pytest.mark.asyncio
async def test_xfyun_missing_creds():
    p = XfyunProvider()
    assert await p.transcribe(PCM, sample_rate=16000, creds=SttCredentials()) == ""
    assert (
        await p.transcribe(PCM, sample_rate=16000, creds=SttCredentials(app_id="a", api_key="k"))
        == ""
    )
    assert (
        await p.transcribe(
            PCM,
            sample_rate=16000,
            creds=SttCredentials(app_id="a", api_key="k", api_secret="  "),
        )
        == ""
    )


@pytest.mark.asyncio
async def test_xfyun_bad_audio():
    p = XfyunProvider()
    creds = SttCredentials(app_id="a", api_key="k", api_secret="s")
    assert await p.transcribe("a", sample_rate=16000, creds=creds) == ""


@pytest.mark.asyncio
async def test_xfyun_requires_websockets():
    p = XfyunProvider()
    creds = SttCredentials(app_id="a", api_key="k", api_secret="s")
    with patch.dict(sys.modules, {"websockets": None}):
        assert await p.transcribe(PCM, sample_rate=16000, creds=creds) == ""


@pytest.mark.asyncio
async def test_xfyun_success_single_frame(monkeypatch):
    ws = _FakeWS([_msg(words=["hello", "world"], status=2)])
    captured = _install_ws(monkeypatch, ws)
    p = XfyunProvider()
    out = await p.transcribe(
        PCM, sample_rate=16000, creds=SttCredentials(app_id="a", api_key="k", api_secret="s")
    )
    assert out == "helloworld"
    assert captured["url"].startswith("wss://")
    frame = json.loads(ws.sent[0])
    assert frame["common"]["app_id"] == "a"
    assert frame["business"]["language"] == "zh_cn"
    assert frame["data"]["status"] == 2


@pytest.mark.asyncio
async def test_xfyun_multi_frame_concat(monkeypatch):
    ws = _FakeWS([_msg(words=["ni"], status=1), _msg(words=["hao"], status=2)])
    _install_ws(monkeypatch, ws)
    p = XfyunProvider()
    out = await p.transcribe(
        PCM, sample_rate=16000, creds=SttCredentials(app_id="a", api_key="k", api_secret="s")
    )
    assert out == "nihao"


@pytest.mark.asyncio
async def test_xfyun_code_error_returns_empty(monkeypatch):
    ws = _FakeWS([json.dumps({"code": 101, "message": "auth fail"})])
    _install_ws(monkeypatch, ws)
    p = XfyunProvider()
    assert (
        await p.transcribe(
            PCM, sample_rate=16000, creds=SttCredentials(app_id="a", api_key="k", api_secret="s")
        )
        == ""
    )


@pytest.mark.asyncio
async def test_xfyun_empty_result(monkeypatch):
    ws = _FakeWS([_msg(words=[], status=2)])
    _install_ws(monkeypatch, ws)
    p = XfyunProvider()
    assert (
        await p.transcribe(
            PCM, sample_rate=16000, creds=SttCredentials(app_id="a", api_key="k", api_secret="s")
        )
        == ""
    )


@pytest.mark.asyncio
async def test_xfyun_exception_returns_empty(monkeypatch):
    ws = _FakeWS([], send_exc=RuntimeError("ws down"))
    _install_ws(monkeypatch, ws)
    p = XfyunProvider()
    assert (
        await p.transcribe(
            PCM, sample_rate=16000, creds=SttCredentials(app_id="a", api_key="k", api_secret="s")
        )
        == ""
    )
    ws2 = _FakeWS([RuntimeError("recv fail")])
    _install_ws(monkeypatch, ws2)
    assert (
        await p.transcribe(
            PCM, sample_rate=16000, creds=SttCredentials(app_id="a", api_key="k", api_secret="s")
        )
        == ""
    )
