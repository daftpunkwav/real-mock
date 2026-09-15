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
