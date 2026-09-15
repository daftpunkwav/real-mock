"""JSON response tests for apps/api/src/realmock/platform/capabilities/ai/llm/client/json_response.py.

Covers: parse_chat_json direct/retry/empty/think-tag/fence/prose/repair/autoclose
branches and _auto_close_brackets variants.

Conventions: no real network (chat callable faked with AsyncMock); asyncio_mode=auto.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from realmock.platform.capabilities.ai.llm.client import json_response as jr_mod
from realmock.platform.capabilities.ai.llm.client.json_response import _auto_close_brackets, parse_chat_json



@pytest.mark.asyncio
async def test_parse_chat_json_direct() -> None:
    chat = AsyncMock(return_value='{"a": 1}')
    out = await parse_chat_json(chat, [{"role": "user", "content": "hi"}], 0.5, 64)
    assert out == {"a": 1}
    _, kwargs = chat.call_args
    assert kwargs["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_parse_chat_json_empty_then_retry() -> None:
    chat = AsyncMock(side_effect=["", '{"b": 2}'])
    out = await parse_chat_json(chat, [{"role": "user", "content": "hi"}], 0.5, 64)
    assert out == {"b": 2}
    assert chat.call_count == 2
    retry_msgs = chat.call_args[0][0]
    assert len(retry_msgs) == 2
    assert "JSON" in retry_msgs[1]["content"]


@pytest.mark.asyncio
async def test_parse_chat_json_still_empty_raises() -> None:
    chat = AsyncMock(side_effect=["", "   "])
    with pytest.raises(ValueError, match="empty content"):
        await parse_chat_json(chat, [], 0.5, 64)


@pytest.mark.asyncio
async def test_parse_chat_json_strips_think_tags() -> None:
    chat = AsyncMock(return_value="<think>hmm</think> <thinking>x</thinking> {\"a\": 1}")
    assert await parse_chat_json(chat, [], 0.5, 64) == {"a": 1}
    chat2 = AsyncMock(return_value="<think>unclosed {\"a\": 2}")
    assert await parse_chat_json(chat2, [], 0.5, 64) == {"a": 2}


@pytest.mark.asyncio
async def test_parse_chat_json_fences_and_prose() -> None:
    chat = AsyncMock(return_value='```json\n{"a": 1}\n```')
    assert await parse_chat_json(chat, [], 0.5, 64) == {"a": 1}
    chat2 = AsyncMock(return_value='here you go: {"a": 2} hope it helps')
    assert await parse_chat_json(chat2, [], 0.5, 64) == {"a": 2}


@pytest.mark.asyncio
async def test_parse_chat_json_repairs_and_autocloses() -> None:
    chat = AsyncMock(return_value='{"a": 1,}')
    assert await parse_chat_json(chat, [], 0.5, 64) == {"a": 1}
    chat2 = AsyncMock(return_value='{"a": {"b": [1, 2')
    assert await parse_chat_json(chat2, [], 0.5, 64) == {"a": {"b": [1, 2]}}


@pytest.mark.asyncio
async def test_parse_chat_json_rejects_non_object_and_garbage() -> None:
    with pytest.raises(ValueError, match="must be object"):
        await parse_chat_json(AsyncMock(return_value="[1, 2]"), [], 0.5, 64)
    with pytest.raises(json.JSONDecodeError):
        await parse_chat_json(AsyncMock(return_value="just some words"), [], 0.5, 64)


def test_auto_close_brackets_variants() -> None:
    assert _auto_close_brackets('{"a": 1}') == '{"a": 1}'
    assert _auto_close_brackets('{"a": 1') == '{"a": 1}'
    assert _auto_close_brackets('{"a": [1, 2') == '{"a": [1, 2]}'
    assert _auto_close_brackets('{"a": "x') == '{"a": "x"}'
    fixed = _auto_close_brackets('{"a": "x\\"y')
    assert fixed.endswith('"}')
    assert json.loads(fixed) == {"a": 'x"y'}
    assert jr_mod.__all__ == ["parse_chat_json"]
