"""Token estimation tests for apps/api/src/realmock/platform/capabilities/ai/context/estimation.py.

Covers: estimate_tokens/estimate_messages_tokens/estimate_image_url_tokens,
select_vision_urls, _plain_text and _omitted_digest branches.

Conventions: pure functions, no network; asyncio_mode=auto.
"""

from __future__ import annotations

from realmock.platform.capabilities.ai.context import estimation as est_mod
from realmock.platform.capabilities.ai.context.estimation import (
    _image_item_tokens,
    _omitted_digest,
    _plain_text,
    estimate_image_url_tokens,
    estimate_messages_tokens,
    estimate_tokens,
    select_vision_urls,
)



def test_estimate_tokens_and_messages() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("hello world") >= 1
    assert estimate_tokens("你好世界") > estimate_tokens("abcd")
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "user", "content": None},
        {"role": "user", "content": [{"text": "a"}, {"image_url": {"url": "u" * 100}}, "raw"]},
        {"role": "user", "content": [{"image_url": "http://x/i.png"}]},
        "junk",
        5,
    ]
    assert estimate_messages_tokens(msgs) > 0


def test_image_tokens_and_vision_select() -> None:
    assert estimate_image_url_tokens("") == 0
    assert estimate_image_url_tokens("u") == est_mod.MIN_IMAGE_ITEM_TOKENS
    assert select_vision_urls([], 100) == []
    assert select_vision_urls([""], 100) == []
    huge = "z" * 10000
    assert select_vision_urls([huge], 100) == [huge]  # first page always kept
    two = select_vision_urls(["a" * 100, "b" * 100], 100)
    assert two == ["a" * 100]  # second exceeds the vision share
    assert _image_item_tokens({"image_url": {"url": "http://x"}}) > 0
    assert _image_item_tokens({"image_url": "http://x"}) > 0
    assert _image_item_tokens({"text": "hi"}) == 0


def test_plain_text_and_digest() -> None:
    assert _plain_text([{"text": "a"}, 5, {"nope": 1}]) == "a 5"
    assert _plain_text(None) == ""
    assert _plain_text("x") == "x"
    assert _omitted_digest([{"role": "system", "content": "s"}]) == ""
    short = [
        {"role": "user", "content": "u1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": ""},
    ]
    digest = _omitted_digest(short)
    assert "u1" in digest and "a1" in digest
    assert "omitted in the middle" not in digest
    many = [{"role": "user", "content": f"question number {i}"} for i in range(8)]
    many += [{"role": "assistant", "content": f"answer number {i}"} for i in range(4)]
    digest2 = _omitted_digest(many)
    assert "omitted in the middle" in digest2
    assert len(_omitted_digest(many, max_lines=1)) <= 90
