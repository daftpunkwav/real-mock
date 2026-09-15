"""Inline tool-call extra tests for apps/api/src/realmock/platform/capabilities/ai/llm/inline_tool_call.py.

Covers: partial open-tag buffering, blank-window wait/release, full-blank passthrough,
unclosed-block flush conversion, oversized passthrough and quiz-renderer variants.

Conventions: pure parser, no network; asyncio_mode=auto.
"""

from __future__ import annotations

from realmock.platform.capabilities.ai.llm.inline_tool_call import (
    InlineToolCallCleaner,
    _default_quiz_renderer,
)



def test_partial_open_tag_buffered_across_feeds() -> None:
    c = InlineToolCallCleaner()
    assert c.feed("hello <tool_ca") == "hello "
    out = c.feed('ll><invoke name="quiz"><question>Q?</question></tool_call>tail')
    assert out == "Q?tail"
    assert c.flush() == ""


def test_blank_window_waits_then_releases_as_text() -> None:
    c = InlineToolCallCleaner()
    assert c.feed("a<tool_call>  ") == ""  # blank so far → wait for more data
    assert c.feed("  hello") == "a<tool_call>    hello"
    assert c.flush() == ""


def test_all_blank_window_is_not_a_tool_block() -> None:
    c = InlineToolCallCleaner()
    blob = "<tool_call>" + " " * 70 + "text"
    assert c.feed(blob) == blob  # full blank window → tag released as text
    assert c.flush() == ""


def test_unclosed_block_converted_on_flush_and_oversized_passes_through() -> None:
    c = InlineToolCallCleaner()
    c.feed('<tool_call><invoke name="quiz"><question>QQ?</question>')
    assert c.flush() == "QQ?"
    big = InlineToolCallCleaner()
    blob = '<tool_call><invoke name="quiz">' + "x" * 5000
    # Oversized unclosed block passes through as body text (open tag consumed as block start).
    assert big.feed(blob) == blob[len("<tool_call>"):]
    assert big.flush() == ""
    assert _default_quiz_renderer("") == ""
    assert _default_quiz_renderer("Q") == "Q"
    custom = InlineToolCallCleaner(quiz_renderer=lambda q: f"[{q}]")
    out = custom.feed('<tool_call><invoke name="quiz"><question>Q</question></tool_call>')
    assert out == "[Q]"
    assert custom.flush() == ""
