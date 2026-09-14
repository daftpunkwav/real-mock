"""Grounded JSON repair for resume review — never invent from an empty prompt."""

from __future__ import annotations

import asyncio

import pytest

from realmock.domains.resume.agents.review import (
    _extract_json_object,
    evidence_for_repair,
    finalize_review_json,
)
from realmock.platform.capabilities.ai.agent import LoopResult
from realmock.platform.core.errors import ApiBusinessError


class _FakeLLM:
    def __init__(self) -> None:
        self.repair_user: str = ""

    async def chat(self, messages, **kwargs):
        del messages, kwargs
        return "compressed-evidence"

    async def chat_json(self, messages, **kwargs):
        del kwargs
        self.repair_user = str(messages[1]["content"])
        return {"headline": "from-evidence", "score": 70}


def test_evidence_for_repair_keeps_overview_and_tools() -> None:
    blob = evidence_for_repair(
        [
            {"role": "system", "content": "ignore"},
            {"role": "user", "content": "Review Ada Lee, product manager"},
            {"role": "tool", "name": "web_search", "content": "PM JD hits"},
        ],
        "not json",
    )
    assert "Ada Lee" in blob
    assert "PM JD hits" in blob
    assert "DRAFT:" in blob


def test_evidence_for_repair_marks_images_without_data_url() -> None:
    blob = evidence_for_repair(
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "page overview"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
                ],
            }
        ],
        "",
    )
    assert "page overview" in blob
    assert "AAAA" not in blob
    assert "[attached page image]" in blob


def test_finalize_repair_sends_evidence_not_empty_prompt() -> None:
    llm = _FakeLLM()
    loop = LoopResult(
        messages=[
            {"role": "user", "content": "Review Ada Lee resume"},
            {"role": "tool", "content": "github repo exists"},
        ],
        final_content="not-json",
        tool_used=True,
    )
    payload = asyncio.run(finalize_review_json(loop, llm, locale="en", max_output=512))
    assert payload["headline"] == "from-evidence"
    assert "Ada Lee" in llm.repair_user
    assert "already gathered" not in llm.repair_user.lower()


def test_finalize_silent_empty_loop_raises_c0001() -> None:
    llm = _FakeLLM()
    loop = LoopResult(messages=[], final_content=None, tool_used=False)
    with pytest.raises(ApiBusinessError) as exc:
        asyncio.run(finalize_review_json(loop, llm, locale="zh-CN", max_output=512))
    assert exc.value.error_code == "C0001"
    assert llm.repair_user == ""


def test_finalize_valid_json_skips_repair() -> None:
    llm = _FakeLLM()
    loop = LoopResult(
        messages=[{"role": "user", "content": "overview"}],
        final_content='{"headline": "direct", "score": 80}',
        tool_used=True,
    )
    payload = asyncio.run(finalize_review_json(loop, llm, locale="en", max_output=512))
    assert payload["headline"] == "direct"
    assert llm.repair_user == ""


def test_extract_json_recovers_object_wrapped_in_prose() -> None:
    noisy = (
        "Let me lay out the analysis. Key points:\n"
        '- 量化扎实（P95 1.2s、328 用例）\n'
        '{"score": 77, "headline": "wrapped", "dimension_scores": {"a": {"score": 1}}}\n'
        "以上为最终结论。"
    )
    data = _extract_json_object(noisy)
    assert data == {"score": 77, "headline": "wrapped", "dimension_scores": {"a": {"score": 1}}}


def test_extract_json_tolerates_braces_and_escapes_inside_strings() -> None:
    noisy = 'noise {"overall_narrative": "含 \\"引号\\" 与 {花括号} 的叙述", "score": 1} 尾部'
    data = _extract_json_object(noisy)
    assert data is not None
    assert data["score"] == 1
    assert "{花括号}" in data["overall_narrative"]


def test_extract_json_prefers_the_key_richest_draft() -> None:
    noisy = '{"draft": 1} middle {"score": 5, "headline": "full", "skills": ["a", "b"]} end'
    data = _extract_json_object(noisy)
    assert data is not None
    assert data["headline"] == "full"


def test_extract_json_returns_none_for_garbage_and_empty() -> None:
    assert _extract_json_object("") is None
    assert _extract_json_object(None) is None
    assert _extract_json_object("no braces at all") is None
    assert _extract_json_object("{ not json }") is None
