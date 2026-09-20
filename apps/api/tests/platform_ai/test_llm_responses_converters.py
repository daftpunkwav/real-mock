"""Responses converter tests for apps/api/src/realmock/platform/capabilities/ai/llm/client/responses_converters.py.

Covers: _responses_input (system/tool/assistant mapping) and _responses_tools shapes.

Conventions: pure functions, no network; asyncio_mode=auto.
"""

from __future__ import annotations

from realmock.platform.capabilities.ai.llm.client import responses_converters as rc



def test_responses_input_tool_and_assistant_calls() -> None:
    out = rc._responses_input([
        {"role": "system", "content": "sys"},
        {"role": "tool", "tool_call_id": "c9", "content": "ok"},
        {"role": "tool"},
        {
            "role": "assistant",
            "content": "thinking aloud",
            "tool_calls": [
                {"id": "t1", "function": {"name": "quiz", "arguments": {"n": 2}}},
                {"id": "", "function": {}},
            ],
        },
        {"role": "assistant", "content": "plain"},
        {"content": None},
    ])
    assert out[0] == {"type": "function_call_output", "call_id": "c9", "output": "ok"}
    assert out[1] == {"type": "function_call_output", "call_id": "", "output": ""}
    assert out[2] == {"role": "assistant", "content": "thinking aloud"}
    assert out[3]["type"] == "function_call"
    assert out[3]["arguments"] == '{"n": 2}'
    assert out[4] == {"type": "function_call", "call_id": "", "name": "", "arguments": "{}"}
    assert out[5] == {"role": "assistant", "content": "plain"}
    assert out[6] == {"role": "user", "content": ""}


def test_responses_tools_shapes() -> None:
    assert rc._responses_tools(None) is None
    assert rc._responses_tools([]) is None
    out = rc._responses_tools([
        {"type": "function", "function": {"name": "quiz", "description": "d"}},
        {"name": "bare"},
        {"type": "function", "function": ["bad"]},
    ])
    assert out == [
        {"type": "function", "name": "quiz", "description": "d", "parameters": {"type": "object"}},
        {"type": "function", "name": "bare", "description": "", "parameters": {"type": "object"}},
    ]


def test_responses_input_converts_user_multimodal_parts() -> None:
    out = rc._responses_input([
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "review this"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAA"}},
                {"type": "image_url", "image_url": "https://example.com/p.png"},
                {"type": "image_url", "image_url": {"url": ""}},
                "not-a-dict",
                {"type": "input_file", "file_id": "f1"},
            ],
        },
    ])
    assert out == [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "review this"},
                {"type": "input_image", "image_url": "data:image/png;base64,AAA"},
                {"type": "input_image", "image_url": "https://example.com/p.png"},
                {"type": "input_file", "file_id": "f1"},
            ],
        },
    ]


def test_responses_input_keeps_assistant_and_string_content() -> None:
    out = rc._responses_input([
        {"role": "assistant", "content": [{"type": "text", "text": "kept verbatim"}]},
        {"role": "user", "content": "plain string"},
        {"role": "user", "content": []},
        {"content": None},
    ])
    assert out[0] == {"role": "assistant", "content": [{"type": "text", "text": "kept verbatim"}]}
    assert out[1] == {"role": "user", "content": "plain string"}
    assert out[2] == {"role": "user", "content": ""}
    assert out[3] == {"role": "user", "content": ""}
