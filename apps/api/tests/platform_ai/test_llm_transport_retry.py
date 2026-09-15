"""Transport retry tests for apps/api/src/realmock/platform/capabilities/ai/llm/client/base.py.

Covers: _extract_message_text, _is_local_allowed/_require_https env gates and
_retry_request (429/5xx/connect-error/stream-close/exhaustion paths).

Conventions: no real network (httpx/pinned client mocked); asyncio_mode=auto.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from realmock.platform.capabilities.ai.llm.client import base as base_mod


# ── _extract_message_text ──


def test_extract_none_and_non_dict() -> None:
    assert base_mod._extract_message_text(None) == ""
    assert base_mod._extract_message_text("x") == ""  # type: ignore[arg-type]
    assert base_mod._extract_message_text({}) == ""


def test_extract_str_content() -> None:
    assert base_mod._extract_message_text({"content": "hello"}) == "hello"


def test_extract_list_mixed_parts() -> None:
    msg = {"content": [{"type": "text", "text": "a"}, "b", {"type": "other"}]}
    assert base_mod._extract_message_text(msg) == "ab"


def test_extract_list_empty_falls_to_reasoning() -> None:
    assert base_mod._extract_message_text({"content": [], "reasoning_content": "rc"}) == "rc"


def test_extract_reasoning_keys() -> None:
    assert base_mod._extract_message_text({"reasoning_content": "r1"}) == "r1"
    assert base_mod._extract_message_text({"reasoning": "r2"}) == "r2"
    assert base_mod._extract_message_text({"output_text": "o"}) == "o"


def test_extract_whitespace_str_passthrough() -> None:
    # Blank content with no fallback hits the final isinstance(content, str) branch.
    # strip_emojis collapses runs of spaces, so 3 spaces become 1.
    assert base_mod._extract_message_text({"content": "   "}) == " "


def test_extract_emoji_stripped() -> None:
    assert "😀" not in base_mod._extract_message_text({"content": "hi 😀"})


def test_extract_non_str_content_returns_empty() -> None:
    assert base_mod._extract_message_text({"content": 123}) == ""
    assert base_mod._extract_message_text({"foo": "bar"}) == ""


# ── env helpers ──


def test_is_local_allowed_and_require_https(monkeypatch: pytest.MonkeyPatch) -> None:
    s = MagicMock()
    s.allow_local_llm = True
    s.is_prod = False
    monkeypatch.setattr("realmock.platform.capabilities.ai.llm.client.base.get_settings", lambda: s)
    assert base_mod._is_local_allowed() is True
    assert base_mod._require_https() is False
    s.allow_local_llm = False
    s.is_prod = True
    assert base_mod._is_local_allowed() is False
    assert base_mod._require_https() is True


# ── _retry_request ──


def _ok_response(status: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.request = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.aclose = AsyncMock()
    return resp


@pytest.mark.asyncio
async def test_retry_success_first_try() -> None:
    resp = _ok_response(200)
    out = await base_mod._retry_request(lambda: _coro(resp))
    assert out is resp


async def _coro(value: Any) -> Any:
    return value


async def _raise(exc: Exception) -> Any:
    raise exc


@pytest.mark.asyncio
async def test_retry_429_exception_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base_mod.asyncio, "sleep", AsyncMock())
    err_resp = MagicMock(status_code=429)
    exc = httpx.HTTPStatusError("429", request=MagicMock(), response=err_resp)
    calls = {"n": 0}

    async def _factory() -> Any:
        calls["n"] += 1
        if calls["n"] < 3:
            raise exc
        return _ok_response(200)

    out = await base_mod._retry_request(_factory, max_retries=3, backoff=0.1)
    assert out.status_code == 200
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_retry_4xx_no_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeper = AsyncMock()
    monkeypatch.setattr(base_mod.asyncio, "sleep", sleeper)
    err_resp = MagicMock(status_code=400)
    exc = httpx.HTTPStatusError("400", request=MagicMock(), response=err_resp)
    with pytest.raises(httpx.HTTPStatusError):
        await base_mod._retry_request(lambda: _raise(exc), max_retries=3)
    assert sleeper.await_count == 0


@pytest.mark.asyncio
async def test_retry_5xx_status_code_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base_mod.asyncio, "sleep", AsyncMock())
    seq = [_ok_response(500), _ok_response(200)]
    it = iter(seq)
    out = await base_mod._retry_request(lambda: _coro(next(it)), max_retries=3)
    assert out.status_code == 200


@pytest.mark.asyncio
async def test_retry_status_exhausted_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base_mod.asyncio, "sleep", AsyncMock())
    resp = _ok_response(500)
    resp.raise_for_status.side_effect = httpx.HTTPStatusError("500", request=MagicMock(), response=resp)
    with pytest.raises(httpx.HTTPStatusError):
        await base_mod._retry_request(lambda: _coro(resp), max_retries=1)


@pytest.mark.asyncio
async def test_retry_connect_error_then_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base_mod.asyncio, "sleep", AsyncMock())
    calls = {"n": 0}

    async def _factory() -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("down")
        return _ok_response(200)

    out = await base_mod._retry_request(_factory, max_retries=2)
    assert out.status_code == 200


@pytest.mark.asyncio
async def test_retry_connect_error_exhausted() -> None:
    with pytest.raises(httpx.ConnectError):
        await base_mod._retry_request(
            lambda: _raise(httpx.ConnectError("down")), max_retries=1, backoff=0.01
        )


@pytest.mark.asyncio
async def test_retry_read_timeout_write_remote_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base_mod.asyncio, "sleep", AsyncMock())
    for exc in (
        httpx.ReadTimeout("t"),
        httpx.WriteError("w"),
        httpx.RemoteProtocolError("p"),
    ):
        with pytest.raises(type(exc)):
            await base_mod._retry_request(lambda: _raise(exc), max_retries=0)


@pytest.mark.asyncio
async def test_retry_is_stream_closes_before_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base_mod.asyncio, "sleep", AsyncMock())
    bad = _ok_response(503)
    good = _ok_response(200)
    seq = [bad, good]
    it = iter(seq)
    out = await base_mod._retry_request(lambda: _coro(next(it)), max_retries=2, is_stream=True)
    assert out is good
    assert bad.aclose.await_count == 1


@pytest.mark.asyncio
async def test_retry_is_stream_close_failure_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base_mod.asyncio, "sleep", AsyncMock())
    bad = _ok_response(500)
    bad.aclose = AsyncMock(side_effect=OSError("nope"))
    good = _ok_response(200)
    seq = [bad, good]
    it = iter(seq)
    out = await base_mod._retry_request(lambda: _coro(next(it)), max_retries=2, is_stream=True)
    assert out is good


@pytest.mark.asyncio
async def test_retry_exception_is_stream_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(base_mod.asyncio, "sleep", AsyncMock())
    err_resp = MagicMock()
    err_resp.status_code = 500
    err_resp.aclose = AsyncMock()
    exc = httpx.HTTPStatusError("500", request=MagicMock(), response=err_resp)
    calls = {"n": 0}

    async def _factory() -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise exc
        return _ok_response(200)

    out = await base_mod._retry_request(_factory, max_retries=2, is_stream=True)
    assert out.status_code == 200
    assert err_resp.aclose.await_count == 1


@pytest.mark.asyncio
async def test_retry_exception_is_stream_close_raises_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(base_mod.asyncio, "sleep", AsyncMock())
    err_resp = MagicMock()
    err_resp.status_code = 500
    err_resp.aclose = AsyncMock(side_effect=RuntimeError("bad"))
    exc = httpx.HTTPStatusError("500", request=MagicMock(), response=err_resp)

    async def _factory() -> Any:
        raise exc

    with pytest.raises(httpx.HTTPStatusError):
        await base_mod._retry_request(_factory, max_retries=0, is_stream=True)


@pytest.mark.asyncio
async def test_retry_exception_is_stream_close_failure_then_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(base_mod.asyncio, "sleep", AsyncMock())
    err_resp = MagicMock()
    err_resp.status_code = 500
    err_resp.aclose = AsyncMock(side_effect=OSError("close-fail"))
    exc = httpx.HTTPStatusError("500", request=MagicMock(), response=err_resp)
    calls = {"n": 0}

    async def _factory() -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise exc
        return _ok_response(200)

    out = await base_mod._retry_request(_factory, max_retries=2, is_stream=True)
    assert out.status_code == 200
    assert err_resp.aclose.await_count == 1


@pytest.mark.asyncio
async def test_retry_no_response_status_zero_raises() -> None:
    exc = httpx.HTTPStatusError("x", request=MagicMock(), response=None)
    with pytest.raises(httpx.HTTPStatusError):
        await base_mod._retry_request(lambda: _raise(exc), max_retries=2, backoff=0.01)
