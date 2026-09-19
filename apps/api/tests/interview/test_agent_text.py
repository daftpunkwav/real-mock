"""Agent text tests for src/realmock/domains/interview/agents/agent_text.py.

Covers: markers, think-block stripping, ThinkStreamFilter token splits
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations


from realmock.domains.interview.agents.agent_text import (
    INTERVIEW_COMPLETE_MARKER,
    PHASE_COMPLETE_MARKER,
    ThinkStreamFilter,
    has_marker,
    strip_markers,
    strip_think_blocks,
)


def test_has_marker() -> None:
    assert has_marker(f"hello {PHASE_COMPLETE_MARKER}", PHASE_COMPLETE_MARKER) is True
    assert has_marker("hello", PHASE_COMPLETE_MARKER) is False
    assert has_marker(f"x {INTERVIEW_COMPLETE_MARKER}", INTERVIEW_COMPLETE_MARKER) is True


def test_strip_think_blocks_complete_and_case_insensitive() -> None:
    text = "Hello <think>secret reasoning</think> world"
    assert strip_think_blocks(text) == "Hello  world"
    upper = "A <THINK>hidden</THINK> B"
    assert "hidden" not in strip_think_blocks(upper)
    thinking = "A <thinking>deep</thinking> B"
    out = strip_think_blocks(thinking)
    assert "deep" not in out and "A" in out and "B" in out


def test_strip_think_blocks_unclosed_discards_tail() -> None:
    assert strip_think_blocks("Hello <think>unclosed tail") == "Hello "
    assert strip_think_blocks("Hello <thinking>tail") == "Hello "


def test_strip_think_blocks_empty() -> None:
    assert strip_think_blocks("") == ""
    assert strip_think_blocks("no tags here") == "no tags here"


def test_strip_markers_removes_all() -> None:
    text = (
        f"Hi <think>hide</think> there {PHASE_COMPLETE_MARKER} "
        f"{INTERVIEW_COMPLETE_MARKER} [emotion:smile] end"
    )
    out = strip_markers(text)
    assert "<think>" not in out
    assert PHASE_COMPLETE_MARKER not in out
    assert INTERVIEW_COMPLETE_MARKER not in out
    assert "[emotion:smile]" not in out
    assert "Hi" in out and "end" in out


def test_strip_markers_emotion_variants() -> None:
    for tag in ("[emotion:neutral]", "[emotion:smile]", "[emotion:serious]"):
        assert tag not in strip_markers(f"a {tag} b")


def test_think_stream_filter_passthrough() -> None:
    f = ThinkStreamFilter()
    assert f.feed("hello ") == "hello "
    assert f.feed("world") == "world"
    assert f.flush() == ""


def test_think_stream_filter_empty_token() -> None:
    f = ThinkStreamFilter()
    assert f.feed("") == ""
    assert f.flush() == ""


def test_think_stream_filter_single_token_block() -> None:
    f = ThinkStreamFilter()
    assert f.feed("a <think>secret</think> b") == "a  b"
    assert f.flush() == ""


def test_think_stream_filter_split_open_tag_across_tokens() -> None:
    f = ThinkStreamFilter()
    # Unfinished "<thi" tail is buffered (only the tag prefix), never emitted
    # until the tag completes or is disproven by more input.
    assert f.feed("hello <thi") == "hello "
    assert f.feed("nk>secret</think> world") == " world"


def test_think_stream_filter_partial_prefix_in_long_tail() -> None:
    f = ThinkStreamFilter()
    # A partial tag prefix must stay buffered even when the tail is long;
    # emitting it would disable think filtering for the rest of the stream.
    assert f.feed("hello world <thi") == "hello world "
    assert f.feed("nking>secret</think> tail") == " tail"


def test_think_stream_filter_split_close_tag_keeps_hidden() -> None:
    f = ThinkStreamFilter()
    assert f.feed("visible <think>hidden part") == "visible "
    # Still inside think: closing split across tokens must not leak.
    assert f.feed(" more hidden</thi") == ""
    assert f.feed("nk> after") == " after"


def test_think_stream_filter_unclosed_flush_discards() -> None:
    f = ThinkStreamFilter()
    f.feed("hi <think>never closed")
    assert f.flush() == ""


def test_think_stream_filter_thinking_variant() -> None:
    f = ThinkStreamFilter()
    out = f.feed("a <thinking>inner</thinking> b")
    assert out == "a  b"


def test_think_stream_filter_case_insensitive() -> None:
    f = ThinkStreamFilter()
    assert f.feed("A <THINK>x</THINK> B") == "A  B"


















