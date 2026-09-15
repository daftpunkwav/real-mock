"""Protocol utility tests for apps/api/src/realmock/platform/capabilities/ai/llm/client/protocol_utils.py.

Covers: _json_arguments serialization branches and per-protocol _headers shapes.

Conventions: pure functions, no network; asyncio_mode=auto.
"""

from __future__ import annotations

import json

from realmock.platform.capabilities.ai.llm.client.protocol_utils import (
    _headers,
    _json_arguments,
)
from realmock.platform.core.constants import LLMProtocol


def test_json_arguments_passthrough_str() -> None:
    assert _json_arguments('{"a": 1}') == '{"a": 1}'


def test_json_arguments_dict_dumped() -> None:
    assert json.loads(_json_arguments({"a": 1})) == {"a": 1}


def test_json_arguments_none_becomes_empty_object() -> None:
    assert _json_arguments(None) == "{}"


def test_json_arguments_list_dumped() -> None:
    assert json.loads(_json_arguments([1, 2])) == [1, 2]


def test_json_arguments_unserializable_returns_empty() -> None:
    assert _json_arguments({1, 2}) == "{}"


def test_json_arguments_ensure_ascii_false() -> None:
    assert "中文" in _json_arguments({"k": "中文"})


def test_headers_openai_chat_shape() -> None:
    h = _headers("sk-test", LLMProtocol.OPENAI_CHAT)
    assert h["Authorization"] == "Bearer sk-test"
    assert h["api-key"] == "sk-test"
    assert h["Content-Type"] == "application/json"
    assert "x-api-key" not in h
    assert "anthropic-version" not in h


def test_headers_anthropic_adds_version() -> None:
    h = _headers("sk-ant-test", LLMProtocol.ANTHROPIC_MESSAGES)
    assert h["x-api-key"] == "sk-ant-test"
    assert h["anthropic-version"] == "2023-06-01"
    assert h["Authorization"] == "Bearer sk-ant-test"


def test_headers_responses_has_no_anthropic_keys() -> None:
    h = _headers("k", LLMProtocol.OPENAI_RESPONSES)
    assert "x-api-key" not in h
    assert h["Authorization"] == "Bearer k"
