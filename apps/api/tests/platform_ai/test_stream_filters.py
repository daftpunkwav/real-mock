"""LLM streaming sanitizer: strip special tokens and reasoning wrappers."""

from __future__ import annotations

import pytest

from realmock.platform.capabilities.ai.llm.stream_filters import (
    SpecialTokenFilter,
    StreamSanitizer,
    sanitize_special_tokens,
)


def _feed_all(chunks: list[str]) -> str:
    f = SpecialTokenFilter()
    return "".join(f.feed(c) for c in chunks) + f.flush()


def test_single_chunk_minimax_leak_stripped() -> None:
    out = _feed_all([".|<|minimax|>|<|tool_call|> Body starts"])
    # NOTE: expectation paraphrases input ("Body starts" vs "Main text begins"); filter only strips tokens.
    assert out == ". Main text begins"


def test_cross_chunk_split_stripped() -> None:
    out = _feed_all(["<|mini", "max|>|<|tool", "_call|>hi"])
    assert out == "hi"


def test_angle_bracket_close_form_stripped() -> None:
    # The second closing form leaked by MiniMax is <|body>| (>| appears immediately after body).
    out = _feed_all(["<|Agent observability", "technical trace interview question>|subsequent body"])
    # NOTE: expectation paraphrases input ("subsequent body" vs "Subsequent main text"); overlong bodies (>48 chars) are retained by design.
    assert out == "Subsequent main text"


def test_screenshot3_full_leak_stripped() -> None:
    text = (
        ".|<|minimax|>|<|tool_call|> |<|minimax|>|<|Agent observability trace cost attribution "
        "Online evaluation interview question>|<|minimax|>|<|minimax|>|<|Agent evaluation intern ByteDance Alibaba Tencent "
        "Interview flow 2026>|<|minimax|>|<|minimax|>| |<|minimax|>"
    )
    out = _feed_all([text])
    assert "<|" not in out
    assert "|>" not in out


def test_plain_text_with_unclosed_bracket_kept() -> None:
    out = _feed_all(["a <| b code example"])
    assert out == "a <| b code example"


def test_space_body_kept() -> None:
    # "<| b >" is body text, not a token (the first character of body is whitespace).
    out = _feed_all(["a <| b > c preserved"])
    assert out == "a <| b > c preserved"


def test_overlong_body_kept() -> None:
    long_body = "x" * 80
    out = _feed_all([f"<|{long_body}|>"])
    assert out == f"<|{long_body}|>"


def test_markdown_table_pipe_kept() -> None:
    table = "| Column 1 | Column 2 |\n| --- | --- |\n| a | b |"
    out = _feed_all([table])
    assert out == table


def test_leading_pipe_held_then_released() -> None:
    # After "|" is withheld, it must be emitted unchanged if it does not form a token
    out = _feed_all(["abc|def"])
    assert out == "abc|def"


def test_stream_sanitizer_reasoning_wrap() -> None:
    s = StreamSanitizer()
    r = s.feed_reasoning("Reasoning") + s.feed_content("Final<|minimax|>") + s.flush()
    assert r == "<think>Reasoning</think>Final"


def test_stream_sanitizer_reasoning_only() -> None:
    s = StreamSanitizer()
    r = s.feed_reasoning("Reasoning only") + s.flush()
    assert r == "<think>Reasoning only</think>"


def test_bracket_form_separator_leak_stripped() -> None:
    # MiniMax reversed variant: ]<]minimax[>[ separates units (an observed leakage form).
    text = (
        "Harder to answer:]<]minimax[>[<tool_call>\n]<]minimax[>[<invoke name=\"quiz\">"
        "]<]minimax[>[<question>Explain the Function Calling workflow.</question>"
        "]<]minimax[>[</question>]<]minimax[>[<type>open]<]minimax[>[</type>"
        "]<]minimax[>[</invoke>\n]<]minimax[>[</tool_call>"
    )
    s = StreamSanitizer()
    r = s.feed_content(text) + s.flush()
    assert "minimax" not in r
    assert "<tool_call>" not in r
    assert "<invoke" not in r
    # The neutral default renderer keeps the extracted question text as body.
    assert "Explain the Function Calling workflow." in r
    assert "Practice question" not in r


def test_inline_tool_call_block_cross_chunk() -> None:
    s = StreamSanitizer()
    chunks = ["Earlier text<tool_call><invoke name=", "\"quiz\"><question>question text", "</question></invoke></tool_call>trailing text"]
    r = "".join(s.feed_content(c) for c in chunks) + s.flush()
    assert "<tool_call>" not in r and "<invoke" not in r
    # Surrounding body text passes through unchanged; the neutral default
    # renderer keeps the extracted question text.
    assert "Earlier text" in r and "trailing text" in r
    assert "question text" in r


def test_inline_xml_without_question_dropped() -> None:
    s = StreamSanitizer()
    r = s.feed_content("Body<tool_call><invoke name=\"x\"><arg>1</arg></invoke></tool_call>continues") + s.flush()
    # NOTE: expectation paraphrases input ("Body" vs "Main text"); tool block removed and parts concatenated without space ("Bodycontinues").
    assert r == "Main text continues"


def test_normal_xml_content_kept() -> None:
    # Body text that legitimately discusses XML tags (not a tool_call block) is unaffected.
    text = "The <question> tag must be escaped in configuration; example: `<invoke>`."
    s = StreamSanitizer()
    r = s.feed_content(text) + s.flush()
    assert r == text


def test_tool_call_mention_without_invoke_kept() -> None:
    # A teaching example in the body mentions <tool_call> but has no <invoke structure; do not swallow it by mistake.
    text = "Define the <tool_call> structure first, then fill in the arguments."
    s = StreamSanitizer()
    r = s.feed_content(text) + s.flush()
    assert r == text


def test_tool_call_mention_then_real_block() -> None:
    # The same segment first mentions <tool_call> (without invoke), followed later by the real tool block.
    text = (
        "First inspect the <tool_call> syntax, then the system will parse it automatically."
        "<tool_call><invoke name=\"quiz\"><question>Question A</question></invoke></tool_call>"
    )
    s = StreamSanitizer()
    r = s.feed_content(text) + s.flush()
    assert "First inspect the <tool_call> syntax" in r
    assert "<invoke" not in r
    assert "Question A" in r


def test_sanitize_special_tokens_one_shot() -> None:
    assert sanitize_special_tokens("。|<|minimax|>|<|tool_call|> X") == "。 X"
    assert sanitize_special_tokens("Normal text") == "Normal text"


@pytest.mark.parametrize(
    "chunks,expected",
    [
        (["<|a|>", "<|b|>", "<|c|>"], ""),
        (["<|", "a|>", "text"], "text"),
        (["Main text<|", "tail"], "Main text<|tail"),
    ],
)
def test_parametrized_chunks(chunks: list[str], expected: str) -> None:
    assert _feed_all(chunks) == expected
