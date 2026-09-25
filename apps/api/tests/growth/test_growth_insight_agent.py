"""Growth insight agent tests (normalize / degrade / generation contract).

Conventions: no real network/LLM (mocked or faked); deterministic asserts only.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest


# ---- normalize_growth_insight ----


def test_normalize_clamps_fields() -> None:
    from realmock.domains.growth.agents.insight import normalize_growth_insight

    payload = {
        "headline": "H" * 500,
        "trajectory": "T",
        "trajectory_stage": "RISING",  # case-normalized
        "recurring_weaknesses": [
            {"skill": "sql", "count": "3", "trend": "WORSENING", "advice": "a" * 900},
            {"skill": "", "count": 5},  # dropped: empty skill
            "junk",  # dropped: non-dict
        ],
        "improving_areas": ["debugging", "", 42],
        "resume_gap_insights": ["gap"],
        "training_plan": [
            {"area": "system design", "based_on": "sid 3", "actions": ["draw", "", "review"]},
            {"area": "no actions"},  # dropped
        ],
    }
    out = normalize_growth_insight(payload)
    assert len(out["headline"]) == 200
    assert out["trajectory_stage"] == "rising"
    assert len(out["recurring_weaknesses"]) == 1
    weak = out["recurring_weaknesses"][0]
    assert weak["count"] == 3 and weak["trend"] == "worsening"
    assert len(weak["advice"]) == 400
    assert out["improving_areas"] == ["debugging"]
    assert out["training_plan"] == [
        {"area": "system design", "based_on": "sid 3", "actions": ["draw", "review"]}
    ]


def test_normalize_bad_stage_falls_to_insufficient() -> None:
    from realmock.domains.growth.agents.insight import normalize_growth_insight

    out = normalize_growth_insight({"trajectory_stage": "unknown", "headline": "x", "trajectory": "y"})
    assert out["trajectory_stage"] == "insufficient"


def test_insight_substantive_gate() -> None:
    from realmock.domains.growth.agents.insight import _insight_is_substantive, normalize_growth_insight

    empty = normalize_growth_insight({"headline": "", "trajectory": ""})
    assert not _insight_is_substantive(empty)
    full = normalize_growth_insight(
        {"headline": "h", "trajectory": "t", "recurring_weaknesses": [{"skill": "s"}]}
    )
    assert _insight_is_substantive(full)


# ---- generate_growth_insight (degradation contract) ----


@pytest.fixture
def _two_session_context():
    """Patch context_builder to a fixed two-session context."""
    context = {
        "sessions": [
            {"session_id": 2, "date": "2026-09-01", "role": "后端", "company": "ACME",
             "level": "mid", "overall_score": 72, "verdict": "passed",
             "score_breakdown": {}, "weaknesses": ["sql"], "strengths": [],
             "training_plan": [], "key_problems": []},
            {"session_id": 1, "date": "2026-08-01", "role": "后端", "company": "ACME",
             "level": "mid", "overall_score": 60, "verdict": "failed",
             "score_breakdown": {}, "weaknesses": ["sql"], "strengths": [],
             "training_plan": [], "key_problems": []},
        ],
        "resume_summary": "Latest resume: r.pdf (score 61)",
        "profile_summary": "Candidate profile:\nName: T",
    }
    with patch(
        "realmock.domains.growth.agents.insight.build_growth_context",
        return_value=context,
    ):
        yield context


def test_generate_returns_normalized_insight(_two_session_context) -> None:
    from realmock.domains.growth.agents.insight import generate_growth_insight

    raw = {
        "headline": "稳步上升",
        "trajectory": "sid 2 分数高于 sid 1",
        "trajectory_stage": "rising",
        "recurring_weaknesses": [{"skill": "sql", "count": 2, "trend": "improving", "advice": "练习"}],
        "improving_areas": [],
        "resume_gap_insights": [],
        "training_plan": [{"area": "SQL", "based_on": "sid 1/2", "actions": ["刷题"]}],
    }
    fake_llm = MagicMock()
    fake_llm.chat_json = _async_return(raw)

    async def _run():
        with patch(
            "realmock.domains.growth.agents.insight.LLMClient.from_db", return_value=fake_llm
        ):
            return await generate_growth_insight(MagicMock(), MagicMock(), locale="zh-CN")

    result = asyncio.run(_run())
    assert result is not None
    insight, count = result
    assert count == 2
    assert insight["trajectory_stage"] == "rising"
    assert insight["recurring_weaknesses"][0]["skill"] == "sql"


def _async_return(value):
    async def _call(*args, **kwargs):
        return value
    return _call


def test_generate_skips_without_sessions() -> None:
    from realmock.domains.growth.agents.insight import generate_growth_insight

    with patch(
        "realmock.domains.growth.agents.insight.build_growth_context",
        return_value={"sessions": [], "resume_summary": "", "profile_summary": ""},
    ):
        result = asyncio.run(generate_growth_insight(MagicMock(), MagicMock()))
    assert result is None


def test_generate_none_on_timeout(_two_session_context) -> None:
    from realmock.domains.growth.agents.insight import (
        GROWTH_INSIGHT_TIMEOUT_SECONDS,
        generate_growth_insight,
    )

    async def _hanging(*a, **k):
        await asyncio.sleep(GROWTH_INSIGHT_TIMEOUT_SECONDS + 10)

    fake_llm = MagicMock()
    fake_llm.chat_json = _hanging
    with (
        patch("realmock.domains.growth.agents.insight.LLMClient.from_db", return_value=fake_llm),
        patch("realmock.domains.growth.agents.insight.GROWTH_INSIGHT_TIMEOUT_SECONDS", 0.01),
    ):
        result = asyncio.run(generate_growth_insight(MagicMock(), MagicMock()))
    assert result is None


def test_generate_none_on_bad_json(_two_session_context) -> None:
    from realmock.domains.growth.agents.insight import generate_growth_insight

    fake_llm = MagicMock()
    fake_llm.chat_json = _async_return("not a dict")
    with patch("realmock.domains.growth.agents.insight.LLMClient.from_db", return_value=fake_llm):
        result = asyncio.run(generate_growth_insight(MagicMock(), MagicMock()))
    assert result is None


def test_generate_none_on_empty_shell(_two_session_context) -> None:
    from realmock.domains.growth.agents.insight import generate_growth_insight

    fake_llm = MagicMock()
    fake_llm.chat_json = _async_return({"headline": "", "trajectory": ""})
    with patch("realmock.domains.growth.agents.insight.LLMClient.from_db", return_value=fake_llm):
        result = asyncio.run(generate_growth_insight(MagicMock(), MagicMock()))
    assert result is None


# ---- prompt module hygiene ----


def test_user_message_carries_context_and_language() -> None:
    from realmock.domains.growth.prompts import growth_insight_user_message

    msg = growth_insight_user_message(
        sessions_json=json.dumps([{"session_id": 1}]),
        resume_summary="R",
        profile_summary="P",
        locale="zh-CN",
    )
    assert "session_id" in msg and "R" in msg and "P" in msg
    assert "Simplified Chinese" in msg
    en_msg = growth_insight_user_message(
        sessions_json="[]", resume_summary="", profile_summary="", locale="en"
    )
    assert "in English" in en_msg
