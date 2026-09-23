"""``realmock.platform.capabilities.ai.llm.client`` unit tests: retries + SSRF rejection.

Verify through monkeypatch + mock httpx.AsyncClient:

- 4xx raises immediately without retrying;
- 5xx/429 retries with exponential backoff up to max_retries times;
- Loopback is rejected when allow_local_llm=False;
- Local 127.0.0.1:9999 is allowed when allow_local_llm=True.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from realmock.platform.core.security import UnsafeURLError


def _patch_settings(monkeypatch: pytest.MonkeyPatch, *, allow_local: bool) -> None:
    """Replace get_settings in the client module with MagicMock so allow_local_llm is controllable."""
    s = MagicMock()
    s.allow_local_llm = allow_local
    s.effective_embeddings_base = "https://api.openai.com/v1"
    s.effective_embeddings_key = "sk-test"
    s.effective_embeddings_model = "text-embedding-3-small"
    s.is_prod = not allow_local
    # After splitting the client package, get_settings is distributed across the llm_client_ext / base / openai_transport submodules.
    monkeypatch.setattr("realmock.platform.capabilities.ai.llm.client.llm_client_ext.get_settings", lambda: s)
    monkeypatch.setattr("realmock.platform.capabilities.ai.llm.client.base.get_settings", lambda: s)
    monkeypatch.setattr("realmock.platform.capabilities.ai.llm.client.openai_transport.get_settings", lambda: s)


def _make_client(monkeypatch: pytest.MonkeyPatch, *, allow_local: bool) -> Any:
    _patch_settings(monkeypatch, allow_local=allow_local)
    from realmock.platform.capabilities.ai.llm.client import LLMClient

    return LLMClient(
        api_base="https://api.openai.com/v1",
        api_key="sk-test-key",
        model="gpt-4o",
    )


@pytest.mark.asyncio
async def test_chat_4xx_no_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(monkeypatch, allow_local=False)
    # This test focuses on retry semantics: allow URL validation because real DNS results for the domain differ across environments.
    monkeypatch.setattr("realmock.platform.capabilities.ai.llm.client.llm_client.is_safe_http_url", lambda *a, **kw: True)
    http_client = AsyncMock()
    fake_resp = MagicMock(spec=httpx.Response)
    fake_resp.status_code = 400
    fake_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "400", request=MagicMock(), response=fake_resp
    )
    http_client.post = AsyncMock(return_value=fake_resp)
    with patch("realmock.platform.capabilities.ai.llm.client.openai_transport.make_pinned_async_client") as ac:
        ac.return_value.__aenter__.return_value = http_client
        ac.return_value.__aexit__.return_value = False
        with pytest.raises(httpx.HTTPStatusError):
            await client.chat([{"role": "user", "content": "hi"}])
    # Do not retry 4xx responses: call only once
    assert http_client.post.await_count == 1


@pytest.mark.asyncio
async def test_chat_429_retries_then_returns(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(monkeypatch, allow_local=False)
    # As in test_chat_4xx_no_retry, allow URL validation and focus on retry semantics.
    monkeypatch.setattr("realmock.platform.capabilities.ai.llm.client.llm_client.is_safe_http_url", lambda *a, **kw: True)

    succ = MagicMock(spec=httpx.Response)
    succ.status_code = 200
    succ.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
    succ.raise_for_status = MagicMock()

    http_client = AsyncMock()
    http_client.post = AsyncMock(
        side_effect=[
            httpx.HTTPStatusError(
                "429", request=MagicMock(), response=MagicMock(status_code=429)
            ),
            httpx.HTTPStatusError(
                "429", request=MagicMock(), response=MagicMock(status_code=429)
            ),
            succ,
        ]
    )
    with patch("realmock.platform.capabilities.ai.llm.client.openai_transport.make_pinned_async_client") as ac:
        ac.return_value.__aenter__.return_value = http_client
        ac.return_value.__aexit__.return_value = False
        with patch("realmock.platform.capabilities.ai.llm.retry_policy.asyncio.sleep", new=AsyncMock()):
            text = await client.chat([{"role": "user", "content": "hi"}])
    assert text == "ok"
    assert http_client.post.await_count == 3


@pytest.mark.asyncio
async def test_chat_blocks_loopback_in_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _make_client(monkeypatch, allow_local=False)
    client.api_base = "http://127.0.0.1:9999/v1"
    with pytest.raises(UnsafeURLError):
        await client.chat([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_chat_allows_loopback_in_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    """When allow_local=True, 127.0.0.1:9999 passes the SSRF check and proceeds to the request."""
    client = _make_client(monkeypatch, allow_local=True)
    client.api_base = "http://127.0.0.1:9999/v1"
    succ = MagicMock(spec=httpx.Response)
    succ.status_code = 200
    succ.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
    succ.raise_for_status = MagicMock()
    http_client = AsyncMock()
    http_client.post = AsyncMock(return_value=succ)
    with patch("realmock.platform.capabilities.ai.llm.client.openai_transport.make_pinned_async_client") as ac:
        ac.return_value.__aenter__.return_value = http_client
        ac.return_value.__aexit__.return_value = False
        text = await client.chat([{"role": "user", "content": "hi"}])
    assert text == "ok"


# ── Streaming tool-round assembler (chat_message_stream events → message assembly) ──────────


def test_openai_round_assembler_joins_fragments() -> None:
    """Concatenate tool_calls id/name/arguments fragments by index, producing a message isomorphic to the non-streaming form."""
    from realmock.platform.capabilities.ai.llm.client.assemblers import _OpenAIRoundAssembler

    a = _OpenAIRoundAssembler()
    assert a.feed({"choices": [{"delta": {"reasoning_content": "Thinking"}}]}) == "Thinking"
    a.feed({"choices": [{"delta": {"content": "Main text"}}]})
    a.feed({
        "choices": [{
            "delta": {
                "tool_calls": [
                    {"index": 0, "id": "c1", "function": {"name": "web_search", "arguments": '{"query": "interview'}}
                ]
            }
        }]
    })
    a.feed({"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": ' experiences"}'}}]}}]})
    msg = a.message()
    assert msg["content"] == "Main text"
    assert msg["tool_calls"] == [
        {"id": "c1", "type": "function", "function": {"name": "web_search", "arguments": '{"query": "interview experiences"}'}}
    ]


def test_anthropic_round_assembler_thinking_and_tool_use() -> None:
    """Return thinking_delta immediately; buffer and assemble text and tool_use (partial_json fragments)."""
    from realmock.platform.capabilities.ai.llm.client.assemblers import _AnthropicRoundAssembler

    a = _AnthropicRoundAssembler()
    a.feed({"type": "content_block_start", "index": 0, "content_block": {"type": "thinking"}})
    assert a.feed({
        "type": "content_block_delta", "index": 0,
        "delta": {"type": "thinking_delta", "thinking": "Think about it"},
    }) == "Think about it"
    a.feed({"type": "content_block_start", "index": 1, "content_block": {"type": "text"}})
    a.feed({"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "Hello"}})
    a.feed({
        "type": "content_block_start", "index": 2,
        "content_block": {"type": "tool_use", "id": "t1", "name": "lookup"},
    })
    a.feed({"type": "content_block_delta", "index": 2, "delta": {"type": "input_json_delta", "partial_json": '{"q": '}})
    a.feed({"type": "content_block_delta", "index": 2, "delta": {"type": "input_json_delta", "partial_json": '"x"}'}})
    msg = a.message()
    assert msg["content"] == "Hello"
    assert msg["tool_calls"] == [
        {"id": "t1", "type": "function", "function": {"name": "lookup", "arguments": '{"q": "x"}'}}
    ]


# ── Streaming 429/5xx retries (retry_stream: raise_for_status must run after the retry decision) ──────


def _stream_http_client(status_sequence):
    """Construct a mock HTTP client that returns different responses in sequence (the c.stream context)."""
    http_client = MagicMock()
    calls = {"n": 0}

    def _ok_resp(lines):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.request = MagicMock()
        resp.raise_for_status = MagicMock()

        def _aiter_lines():
            async def _gen():
                for line in lines:
                    yield line
            return _gen()

        resp.aiter_lines = _aiter_lines
        return resp

    def _err_resp(status: int):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = status
        resp.request = MagicMock()
        # aread lets the 400/422 stream_options detection branch read body; an empty body does not contain that field.
        resp.aread = AsyncMock(return_value=b"{}")
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            str(status), request=MagicMock(), response=resp
        )
        return resp

    def _stream(*args, **kwargs):
        idx = calls["n"]
        calls["n"] += 1
        item = status_sequence[min(idx, len(status_sequence) - 1)]
        ctx = MagicMock()
        if isinstance(item, int):
            ctx.__aenter__ = AsyncMock(return_value=_err_resp(item))
        else:
            ctx.__aenter__ = AsyncMock(return_value=_ok_resp(item))
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx

    http_client.stream = _stream
    http_client.calls = calls
    return http_client


def _patch_retry_stream_env(monkeypatch: pytest.MonkeyPatch, http_client) -> None:
    _patch_settings(monkeypatch, allow_local=False)
    monkeypatch.setattr(
        "realmock.platform.capabilities.ai.llm.client.llm_client.is_safe_http_url",
        lambda *a, **kw: True,
    )
    sleeper = AsyncMock()

    async def _no_sleep(_seconds):
        return None

    sleeper.side_effect = _no_sleep
    monkeypatch.setattr("realmock.platform.capabilities.ai.llm.client.retry_stream.asyncio.sleep", sleeper)
    return sleeper


@pytest.mark.asyncio
async def test_chat_message_stream_429_retries_then_emits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Streaming tool-round 429: retry with exponential backoff before any delta is emitted; the second attempt succeeds."""
    client = _make_client(monkeypatch, allow_local=False)
    http_client = _stream_http_client([429, ['data: {"choices":[{"delta":{"content":"hi"}}]}', "data: [DONE]"]])
    _patch_retry_stream_env(monkeypatch, http_client)

    with patch("realmock.platform.capabilities.ai.llm.client.retry_stream.make_pinned_async_client") as ac:
        ac.return_value.__aenter__.return_value = http_client
        ac.return_value.__aexit__.return_value = False
        events = []
        async for ev in client.chat_message_stream([{"role": "user", "content": "hi"}]):
            events.append(ev)

    assert http_client.calls["n"] == 2
    final = [e for e in events if e.get("type") == "message"]
    assert final and final[0]["message"]["content"] == "hi"


@pytest.mark.asyncio
async def test_chat_stream_429_retries_then_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    """Streaming text 429: retry before any token is emitted; the second attempt emits the response body."""
    client = _make_client(monkeypatch, allow_local=False)
    http_client = _stream_http_client([429, ['data: {"choices":[{"delta":{"content":"hi"}}]}', "data: [DONE]"]])
    _patch_retry_stream_env(monkeypatch, http_client)

    with patch("realmock.platform.capabilities.ai.llm.client.retry_stream.make_pinned_async_client") as ac:
        ac.return_value.__aenter__.return_value = http_client
        ac.return_value.__aexit__.return_value = False
        tokens = []
        async for tok in client.chat_stream([{"role": "user", "content": "hi"}]):
            tokens.append(tok)

    assert http_client.calls["n"] == 2
    assert "".join(tokens) == "hi"


@pytest.mark.asyncio
async def test_chat_message_stream_4xx_no_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Streaming 4xx: do not retry; raise immediately."""
    client = _make_client(monkeypatch, allow_local=False)
    http_client = _stream_http_client([400])
    _patch_retry_stream_env(monkeypatch, http_client)

    with patch("realmock.platform.capabilities.ai.llm.client.retry_stream.make_pinned_async_client") as ac:
        ac.return_value.__aenter__.return_value = http_client
        ac.return_value.__aexit__.return_value = False
        with pytest.raises(httpx.HTTPStatusError):
            async for _ in client.chat_message_stream([{"role": "user", "content": "hi"}]):
                pass

    assert http_client.calls["n"] == 1
