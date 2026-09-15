"""Anthropic converter tests for apps/api/src/realmock/platform/capabilities/ai/llm/client/anthropic_converters.py.

Covers: _anthropic_content_blocks (scalar/image/text passthrough), _anthropic_messages
(system skip/tool mapping/assistant variants) and _anthropic_tools/_anthropic_tool_choice shapes.

Conventions: pure functions, no network; asyncio_mode=auto.
"""

from __future__ import annotations

from realmock.platform.capabilities.ai.llm.client import anthropic_converters as ac



def test_content_blocks_scalar_passthrough() -> None:
    assert ac._anthropic_content_blocks("hi") == "hi"
    assert ac._anthropic_content_blocks(None) == ""
    assert ac._anthropic_content_blocks("") == ""


def test_content_blocks_non_dict_part_wrapped() -> None:
    assert ac._anthropic_content_blocks([5]) == [{"type": "text", "text": "5"}]


def test_content_blocks_data_url_image() -> None:
    blocks = ac._anthropic_content_blocks([
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAA"}},
    ])
    assert blocks == [{
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": "AAA"},
    }]


def test_content_blocks_remote_image_and_empty_skipped() -> None:
    blocks = ac._anthropic_content_blocks([
        {"type": "image_url", "image_url": {"url": "https://x/img.png"}},
        {"type": "image_url", "image_url": {"url": ""}},
        {"type": "image_url"},
    ])
    assert blocks == [
        {"type": "image", "source": {"type": "url", "url": "https://x/img.png"}}
    ]


def test_content_blocks_text_and_unknown_passthrough() -> None:
    other = {"type": "input_audio", "data": "zzz"}
    blocks = ac._anthropic_content_blocks([{"type": "text", "text": "hi"}, other])
    assert blocks == [{"type": "text", "text": "hi"}, other]


def test_anthropic_messages_system_skipped_tool_mapped() -> None:
    out = ac._anthropic_messages([
        {"role": "system", "content": "sys"},
        {"role": "tool", "tool_call_id": "c1", "content": "done"},
        {"role": "tool", "content": "noid"},
    ])
    assert out == [
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "c1", "content": "done"}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "", "content": "noid"}]},
    ]


def test_anthropic_messages_assistant_tool_calls_variants() -> None:
    out = ac._anthropic_messages([{
        "role": "assistant",
        "content": "working",
        "tool_calls": [
            {"id": "a", "function": {"name": "quiz", "arguments": '{"q": 1}'}},
            {"id": "b", "function": {"name": "search", "arguments": {"q": "x"}}},
            {"id": "c", "function": {"name": "bad", "arguments": "{oops"}},
            {"id": "", "function": {}},
        ],
    }])
    assert out[0]["role"] == "assistant"
    blocks = out[0]["content"]
    assert blocks[0] == {"type": "text", "text": "working"}
    assert blocks[1] == {"type": "tool_use", "id": "a", "name": "quiz", "input": {"q": 1}}
    assert blocks[2]["input"] == {"q": "x"}
    assert blocks[3] == {"type": "tool_use", "id": "c", "name": "bad", "input": {}}
    assert blocks[4] == {"type": "tool_use", "id": "", "name": "", "input": {}}


def test_anthropic_messages_plain_and_role_fallback() -> None:
    out = ac._anthropic_messages([
        {"role": "user", "content": [{"type": "text", "text": "hi"}]},
        {"content": "norole"},
    ])
    assert out[0] == {"role": "user", "content": [{"type": "text", "text": "hi"}]}
    assert out[1]["role"] == "user"


def test_anthropic_tools_shapes() -> None:
    assert ac._anthropic_tools(None) is None
    assert ac._anthropic_tools([]) is None
    out = ac._anthropic_tools([
        {"type": "function", "function": {"name": "quiz", "description": "d"}},
        {"name": "bare", "parameters": {"type": "object", "properties": {}}},
        {"type": "function", "function": "not-a-dict"},
    ])
    assert out == [
        {"name": "quiz", "description": "d", "input_schema": {"type": "object"}},
        {"name": "bare", "description": "", "input_schema": {"type": "object", "properties": {}}},
    ]


def test_anthropic_tool_choice_shapes() -> None:
    assert ac._anthropic_tool_choice("auto") == {"type": "auto"}
    assert ac._anthropic_tool_choice({"type": "function", "function": {"name": "quiz"}}) == {
        "type": "tool", "name": "quiz",
    }
    passthrough = {"type": "tool", "name": "quiz"}
    assert ac._anthropic_tool_choice(passthrough) == passthrough
