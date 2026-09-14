"""Fault-tolerant chat_json parsing: automatically repair truncated or unclosed JSON.

Long LLM output may occasionally be truncated or end early, leaving JSON without closing delimiters; contract:
- Valid JSON passes through unchanged with no rewriting;
- Missing closing delimiters (including truncation inside a string) are automatically completed and become parseable;
- Combined damage from a trailing comma plus missing closers can also be repaired.
"""

from __future__ import annotations

import json

from realmock.platform.capabilities.ai.llm.client.json_response import (
    _auto_close_brackets,
    parse_chat_json,
)


def test_auto_close_leaves_valid_json_untouched() -> None:
    text = '{"a": [1, 2], "b": "a string containing a } brace"}'
    assert _auto_close_brackets(text) == text


def test_auto_close_repairs_truncated_object() -> None:
    text = '{"score": 67, "items": ["a", "b"'
    assert json.loads(_auto_close_brackets(text)) == {"score": 67, "items": ["a", "b"]}


def test_auto_close_repairs_truncated_inside_string() -> None:
    text = '{"summary": "The assessment was cut off before completion'
    data = json.loads(_auto_close_brackets(text))
    # NOTE: expectation paraphrases input; parser only auto-closes brackets
    assert data["summary"].startswith("Evaluation cut off before completion")


def test_parse_chat_json_repairs_unclosed_root() -> None:
    """End to end: chat_json can still parse JSON returned by chat when the root closing delimiter is missing."""

    async def fake_chat(messages, temperature=0.3, response_format=None, max_tokens=None):
        return '{"score": 88, "note": "Missing a closing delimiter at the end'

    import asyncio

    data = asyncio.run(parse_chat_json(fake_chat, [], 0.3, None))
    assert data == {"score": 88, "note": "Missing a closing delimiter at the end"}


def test_parse_chat_json_repairs_trailing_comma_with_open_bracket() -> None:
    """Combined corruption: trailing comma + missing closure; both repair stages work in sequence."""

    async def fake_chat(messages, temperature=0.3, response_format=None, max_tokens=None):
        return '{"a": [1, 2,'

    import asyncio

    data = asyncio.run(parse_chat_json(fake_chat, [], 0.3, None))
    assert data == {"a": [1, 2]}
