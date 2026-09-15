"""Chat endpoint tests for apps/api/src/realmock/platform/capabilities/ai/llm/client/chat_endpoints.py.

Covers: chat/test_connection/chat_message across protocols with usage recording
and redacted-key error logging.

Conventions: no real network (httpx/pinned client mocked); asyncio_mode=auto.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from realmock.platform.capabilities.ai.llm.client import chat_endpoints as ce_mod
from realmock.platform.capabilities.ai.llm.usage import UsageAccumulator
from realmock.platform.core.constants import LLMProtocol


def _client(**kw: Any) -> MagicMock:
    c = MagicMock()
    c.api_base = "https://api.test/v1"
    c.api_key = "sk-test-1234567890abcdef"
    c.model = "m"
    c.protocol = LLMProtocol.OPENAI_CHAT
    c.usage = UsageAccumulator()
    c._safe_check = MagicMock()
    c._build_url_and_payload = MagicMock(return_value=("https://api.test/v1/chat", {"model": "m"}))
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def _pinned(http_client: MagicMock) -> MagicMock:
    pinned = MagicMock()
    pinned.__aenter__ = AsyncMock(return_value=http_client)
    pinned.__aexit__ = AsyncMock(return_value=False)
    return pinned


@pytest.mark.asyncio
async def test_chat_success_records_usage() -> None:
    client = _client()
    http = AsyncMock()
    resp = MagicMock(spec=httpx.Response)
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"choices": [{"message": {"content": "hi"}}], "usage": {}}
    with (
        patch.object(ce_mod, "make_pinned_async_client", return_value=_pinned(http)),
        patch.object(ce_mod, "_retry_request", new=AsyncMock(return_value=resp)),
    ):
        text = await ce_mod.chat(client, [{"role": "user", "content": "hi"}])
    assert text == "hi"
    assert client._safe_check.called


@pytest.mark.asyncio
async def test_chat_http_error_logs_redacted_key(caplog: pytest.LogCaptureFixture) -> None:
    client = _client()
    http = AsyncMock()
    err_resp = MagicMock()
    err_resp.status_code = 500
    exc = httpx.HTTPStatusError("500", request=MagicMock(), response=err_resp)
    with (
        patch.object(ce_mod, "make_pinned_async_client", return_value=_pinned(http)),
        patch.object(ce_mod, "_retry_request", new=AsyncMock(side_effect=exc)),
        caplog.at_level("WARNING", logger=ce_mod.__name__),
        pytest.raises(httpx.HTTPStatusError),
    ):
        await ce_mod.chat(client, [{"role": "user", "content": "hi"}])
    # Redaction: full key must not appear in warning records.
    assert any("sk-t***cdef" in r.getMessage() for r in caplog.records)
    assert not any("sk-test-1234567890abcdef" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_test_connection_success_truncates() -> None:
    client = _client()
    http = AsyncMock()
    resp = MagicMock(spec=httpx.Response)
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"choices": [{"message": {"content": "x" * 200}}]}
    http.post = AsyncMock(return_value=resp)
    with patch.object(ce_mod, "make_pinned_async_client", return_value=_pinned(http)):
        ok, text = await ce_mod.test_connection(client)
    assert ok is True
    assert len(text) <= 100


@pytest.mark.asyncio
async def test_test_connection_http_error() -> None:
    client = _client()
    http = AsyncMock()
    err_resp = MagicMock()
    err_resp.status_code = 401
    err_resp.text = "unauthorized"
    exc = httpx.HTTPStatusError("401", request=MagicMock(), response=err_resp)
    http.post = AsyncMock(side_effect=exc)
    with patch.object(ce_mod, "make_pinned_async_client", return_value=_pinned(http)):
        ok, text = await ce_mod.test_connection(client)
    assert ok is False
    assert "HTTP 401" in text


@pytest.mark.asyncio
async def test_test_connection_generic_error() -> None:
    client = _client()
    http = AsyncMock()
    http.post = AsyncMock(side_effect=RuntimeError("boom"))
    with patch.object(ce_mod, "make_pinned_async_client", return_value=_pinned(http)):
        ok, text = await ce_mod.test_connection(client)
    assert ok is False
    assert text == "boom"


@pytest.mark.asyncio
async def test_chat_message_with_reasoning() -> None:
    client = _client()
    http = AsyncMock()
    resp = MagicMock(spec=httpx.Response)
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "hello",
                    "tool_calls": [
                        {"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}
                    ],
                    "reasoning_content": "thinking",
                }
            }
        ]
    }
    http.post = AsyncMock(return_value=resp)
    with patch.object(ce_mod, "make_pinned_async_client", return_value=_pinned(http)):
        msg = await ce_mod.chat_message(client, [{"role": "user", "content": "hi"}])
    assert msg["content"] == "hello"
    assert msg["tool_calls"][0]["id"] == "c1"
    assert msg["reasoning"] == "thinking"


@pytest.mark.asyncio
async def test_chat_message_no_reasoning_no_tools() -> None:
    client = _client()
    http = AsyncMock()
    resp = MagicMock(spec=httpx.Response)
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"choices": [{"message": {"content": "hi"}}]}
    http.post = AsyncMock(return_value=resp)
    with patch.object(ce_mod, "make_pinned_async_client", return_value=_pinned(http)):
        msg = await ce_mod.chat_message(client, [{"role": "user", "content": "hi"}])
    assert msg["role"] == "assistant"
    assert "reasoning" not in msg
    assert msg["tool_calls"] == []


@pytest.mark.asyncio
async def test_chat_message_anthropic_and_responses_shapes() -> None:
    for protocol, data in [
        (
            LLMProtocol.ANTHROPIC_MESSAGES,
            {"content": [{"type": "text", "text": "a"}], "usage": {}},
        ),
        (
            LLMProtocol.OPENAI_RESPONSES,
            {"output_text": "b", "output": [], "usage": {}},
        ),
    ]:
        client = _client(protocol=protocol)
        http = AsyncMock()
        resp = MagicMock(spec=httpx.Response)
        resp.raise_for_status = MagicMock()
        resp.json.return_value = data
        http.post = AsyncMock(return_value=resp)
        with patch.object(ce_mod, "make_pinned_async_client", return_value=_pinned(http)):
            msg = await ce_mod.chat_message(client, [{"role": "user", "content": "hi"}])
        assert msg["content"] in ("a", "b")
