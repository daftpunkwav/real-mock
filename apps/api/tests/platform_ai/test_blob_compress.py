"""LLM blob compression must shrink text or mark an explicit excerpt."""

from __future__ import annotations

import asyncio

from realmock.platform.capabilities.ai.context.blobs import compress_text_blob
from realmock.platform.capabilities.ai.context.estimation import (
    estimate_image_url_tokens,
    estimate_messages_tokens,
    select_vision_urls,
)
from realmock.platform.capabilities.ai.llm.defaults import TOOL_OBSERVATION_SOFT_CHARS


class _EchoLLM:
    async def chat(self, messages, **kwargs):
        del kwargs
        return str(messages[-1]["content"])


class _ShortLLM:
    async def chat(self, messages, **kwargs):
        del messages, kwargs
        return "kept facts"


def test_compress_skips_under_soft_cap() -> None:
    text = "short"
    out = asyncio.run(compress_text_blob(None, text))
    assert out == text


def test_compress_without_llm_uses_excerpt_marker() -> None:
    blob = "x" * (TOOL_OBSERVATION_SOFT_CHARS + 50)
    out = asyncio.run(compress_text_blob(None, blob, target_chars=200))
    assert "NO_LLM_EXCERPT" in out
    assert "COMPRESSION_FAILED" not in out


def test_compress_rejects_echo_that_stays_too_long() -> None:
    blob = "y" * (TOOL_OBSERVATION_SOFT_CHARS + 50)
    out = asyncio.run(
        compress_text_blob(_EchoLLM(), blob, soft_chars=100, target_chars=80)
    )
    assert "COMPRESSION_FAILED" in out


def test_compress_accepts_short_summary() -> None:
    blob = "z" * (TOOL_OBSERVATION_SOFT_CHARS + 50)
    out = asyncio.run(compress_text_blob(_ShortLLM(), blob))
    assert out.startswith("[compressed from")
    assert "kept facts" in out


def test_estimate_messages_tokens_counts_images() -> None:
    url = "data:image/png;base64," + ("A" * 3200)
    msgs = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "abc"},
                {"type": "image_url", "image_url": {"url": url}},
            ],
        }
    ]
    total = estimate_messages_tokens(msgs)
    assert total > estimate_image_url_tokens(url)
    assert total >= estimate_image_url_tokens(url)


def test_select_vision_urls_keeps_first_page() -> None:
    huge = "data:image/png;base64," + ("B" * 50_000)
    kept = select_vision_urls([huge, huge, huge], context_window=1_000)
    assert len(kept) >= 1
    assert kept[0] == huge


def test_compact_does_not_insert_empty_omission_note() -> None:
    from realmock.platform.capabilities.ai.context.summarize import compact_with_summary

    huge = "x" * 8000
    msgs = [{"role": "user", "content": huge}]
    out = asyncio.run(compact_with_summary(msgs, max_tokens=10, keep_recent=20))
    joined = " ".join(str(m.get("content")) for m in out)
    assert "Context compression" not in joined
    assert out == msgs
