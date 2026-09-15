"""Say-first streaming extra tests for apps/api/src/realmock/platform/capabilities/ai/llm/say_first_stream.py.

Covers: empty/post-done feeds, non-string say fast-degrade, split escapes,
incomplete/invalid unicode escapes and unknown-escape passthrough.

Conventions: pure parser, no network; asyncio_mode=auto.
"""

from __future__ import annotations

from realmock.platform.capabilities.ai.llm.say_first_stream import SayFirstStreamParser



def test_feed_empty_and_post_done() -> None:
    p = SayFirstStreamParser()
    assert p.feed("") == ""
    p.feed('{"say": "hi", "v": 1}')
    assert p.finish() == ""
    assert p.controls == {"say": "hi", "v": 1}
    assert p.feed("late") == ""  # DONE state swallows further input


def test_non_string_say_single_feed_degrades_fast() -> None:
    body = '{"say": 42, "v": 1}'
    p = SayFirstStreamParser()
    assert p.feed(body) == ""
    assert p.degraded is True
    assert p.finish() == body
    assert p.controls == {"say": 42, "v": 1}


def test_escape_split_across_tokens() -> None:
    p = SayFirstStreamParser()
    assert p.feed('{"say": "ab\\') == "ab"  # trailing backslash waits for next token
    assert p.feed('ncd", "v": 1}') == "\ncd"  # \n completes the escape
    assert p.finish() == ""
    assert p.controls and p.controls["v"] == 1


def test_incomplete_unicode_escape_across_tokens() -> None:
    p = SayFirstStreamParser()
    assert p.feed('{"say": "A\\u4f') == "A"  # \\uXXXX incomplete → wait
    assert p.feed('60B", "v": 1}') == "你B"
    assert p.finish() == ""


def test_invalid_unicode_and_unknown_escapes() -> None:
    p = SayFirstStreamParser()
    out = p.feed('{"say": "X\\uZZZZY", "v": 2}')
    assert "uZZZZ" in out  # undecodable \\uXXXX kept verbatim, never raises
    assert p.finish() == ""
    assert p.controls is None  # raw text is not valid JSON overall
    p2 = SayFirstStreamParser()
    assert p2.feed('{"say": "a\\qb", "v": 3}') == "aqb"
    assert p2.finish() == ""
