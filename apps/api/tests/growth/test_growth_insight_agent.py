"""Growth insight agent tests (normalize / tool loop / degradation contract).

Conventions: no real network/LLM (mocked or faked); deterministic asserts only.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _run(coro):
    return asyncio.run(coro)


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
        "improving_areas": ["debugging", "", 42],  # non-str dropped
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


# ---- tool-loop agent (run_agent_loop stubbed) ----


@pytest.fixture
def _index():
    idx = [
        {"session_id": 2, "date": "2026-09-01", "role": "后端", "company": "ACME",
         "level": "mid", "overall_score": 72, "verdict": "passed"},
        {"session_id": 1, "date": "2026-08-01", "role": "后端", "company": "ACME",
         "level": "mid", "overall_score": 60, "verdict": "failed"},
    ]
    with patch(
        "realmock.domains.growth.agents.insight._build_session_index", return_value=idx
    ):
        yield idx


@pytest.fixture
def _no_side_tools():
    """Resume/profile reads return nothing so the bundle is history-only."""
    with (
        patch(
            "realmock.domains.growth.agents.insight.get_resume_agent_payload",
            return_value=None,
        ),
        patch(
            "realmock.domains.growth.agents.insight.get_default_user_profile",
            return_value=None,
        ),
    ):
        yield


def _fake_loop_result(content: str):
    return SimpleNamespace(final_content=content)


def _analysis_json() -> str:
    return json.dumps(
        {
            "headline": "稳步上升",
            "trajectory": "sid 2 分数高于 sid 1",
            "trajectory_stage": "rising",
            "recurring_weaknesses": [{"skill": "sql", "count": 2, "trend": "improving", "advice": "练习"}],
            "improving_areas": [],
            "resume_gap_insights": [],
            "training_plan": [{"area": "SQL", "based_on": "sid 1/2", "actions": ["刷题"]}],
        },
        ensure_ascii=False,
    )


async def _generate():
    from realmock.domains.growth.agents.insight import generate_growth_insight

    return await generate_growth_insight(MagicMock(), MagicMock(), locale="zh-CN")


def test_generate_parses_loop_json(_index, _no_side_tools) -> None:

    recorded: dict = {}

    async def fake_run_agent_loop(llm, messages, **kwargs):
        recorded["tools"] = [d["function"]["name"] for d in (kwargs["tools"] or [])]
        # Budget lines come from the platform loop; no domain prepare hook.
        recorded["no_prepare"] = kwargs.get("prepare_messages") is None
        recorded["tool_free_final"] = kwargs["final_round_tool_free"]
        recorded["round_retries"] = kwargs["round_retries"]
        return _fake_loop_result(_analysis_json())

    with (
        patch("realmock.domains.growth.agents.insight.LLMClient.from_db", return_value=MagicMock()),
        patch("realmock.domains.growth.agents.insight.run_agent_loop", side_effect=fake_run_agent_loop),
    ):
        result = _run(_generate())

    assert result is not None
    insight, count = result
    assert count == 2
    assert insight["trajectory_stage"] == "rising"
    assert "history_list_sessions" in recorded["tools"]
    assert "history_get_report" in recorded["tools"]
    assert recorded["tool_free_final"] is True
    assert recorded["no_prepare"] is True
    assert recorded["round_retries"] == 1


def test_generate_skips_without_sessions() -> None:

    with patch(
        "realmock.domains.growth.agents.insight._build_session_index", return_value=[]
    ):
        result = _run(_generate())
    assert result is None


def test_generate_none_on_loop_timeout(_index, _no_side_tools) -> None:
    async def _hanging(*a, **k):
        await asyncio.sleep(3600)

    with (
        patch("realmock.domains.growth.agents.insight.LLMClient.from_db", return_value=MagicMock()),
        patch("realmock.domains.growth.agents.insight.run_agent_loop", side_effect=_hanging),
        patch("realmock.domains.growth.agents.insight.GROWTH_LOOP_TIMEOUT_SECONDS", 0.01),
    ):
        result = _run(_generate())
    assert result is None


def test_generate_none_on_unparsable_final(_index, _no_side_tools) -> None:
    async def fake_run_agent_loop(*a, **k):
        return _fake_loop_result("no json here at all")

    with (
        patch("realmock.domains.growth.agents.insight.LLMClient.from_db", return_value=MagicMock()),
        patch("realmock.domains.growth.agents.insight.run_agent_loop", side_effect=fake_run_agent_loop),
    ):
        result = _run(_generate())
    assert result is None


def test_generate_none_on_empty_shell(_index, _no_side_tools) -> None:
    async def fake_run_agent_loop(*a, **k):
        return _fake_loop_result(json.dumps({"headline": "", "trajectory": ""}))

    with (
        patch("realmock.domains.growth.agents.insight.LLMClient.from_db", return_value=MagicMock()),
        patch("realmock.domains.growth.agents.insight.run_agent_loop", side_effect=fake_run_agent_loop),
    ):
        result = _run(_generate())
    assert result is None


def test_generate_salvages_truncated_json(_index, _no_side_tools) -> None:
    """A reply cut off by the output cap still yields the head of the object."""
    raw = _analysis_json()
    truncated = raw[: raw.rindex(",")] + "}"  # cut trailing fields, keep parseable

    async def fake_run_agent_loop(*a, **k):
        return _fake_loop_result(truncated)

    with (
        patch("realmock.domains.growth.agents.insight.LLMClient.from_db", return_value=MagicMock()),
        patch("realmock.domains.growth.agents.insight.run_agent_loop", side_effect=fake_run_agent_loop),
    ):
        result = _run(_generate())
    assert result is not None
    assert result[0]["headline"] == "稳步上升"


# ---- execute_tool_call: circuit breaker + budget ceiling ----


def test_execute_tool_call_circuit_breaker(_index, _no_side_tools) -> None:
    from realmock.domains.growth.agents.insight import _TOOL_CIRCUIT_BREAKER_STREAK

    captured: dict = {}

    async def fake_run_agent_loop(llm, messages, **kwargs):
        captured["execute"] = kwargs["execute"]
        return _fake_loop_result(_analysis_json())

    async def fail_invoke(bundle, name, args, **kwargs):
        return json.dumps({"error": "boom"}), "error"

    with (
        patch("realmock.domains.growth.agents.insight.LLMClient.from_db", return_value=MagicMock()),
        patch("realmock.domains.growth.agents.insight.run_agent_loop", side_effect=fake_run_agent_loop),
        patch("realmock.domains.growth.agents.insight.invoke_with_timeout", side_effect=fail_invoke),
    ):
        _run(_generate())
        execute = captured["execute"]
        same_args = {"session_id": 1}
        for _ in range(_TOOL_CIRCUIT_BREAKER_STREAK):
            raw = _run(execute("history_get_report", same_args))
            assert "boom" in raw
        raw = _run(execute("history_get_report", same_args))
        assert "circuit_open" in raw
        # Different args are never blocked (different workload).
        raw = _run(execute("history_get_report", {"session_id": 2}))
        assert "boom" in raw


def test_execute_tool_call_budget_refusal(_index, _no_side_tools) -> None:
    from realmock.domains.growth.agents.insight import GROWTH_MAX_TOTAL_TOOL_CALLS

    captured: dict = {}

    async def fake_run_agent_loop(llm, messages, **kwargs):
        captured["execute"] = kwargs["execute"]
        return _fake_loop_result(_analysis_json())

    async def ok_invoke(bundle, name, args, **kwargs):
        return json.dumps({"ok": True}), "ok"

    with (
        patch("realmock.domains.growth.agents.insight.LLMClient.from_db", return_value=MagicMock()),
        patch("realmock.domains.growth.agents.insight.run_agent_loop", side_effect=fake_run_agent_loop),
        patch("realmock.domains.growth.agents.insight.invoke_with_timeout", side_effect=ok_invoke),
    ):
        _run(_generate())
        execute = captured["execute"]

        async def _exhaust():
            last = ""
            for i in range(GROWTH_MAX_TOTAL_TOOL_CALLS + 1):
                last = await execute("history_list_sessions", {"limit": i})
            return last

        last = _run(_exhaust())
        assert "tool_budget_exhausted" in last


# ---- prompt module ----


def test_user_message_carries_index_and_language() -> None:
    from realmock.domains.growth.prompts import growth_insight_user_message

    msg = growth_insight_user_message(
        session_index_json=json.dumps([{"session_id": 1}]),
        locale="zh-CN",
    )
    assert "session_id" in msg
    assert "Simplified Chinese" in msg
    assert "history_get_report" in msg
    en_msg = growth_insight_user_message(session_index_json="[]", locale="en")
    assert "in English" in en_msg


def test_generate_none_on_llm_upstream_error(_index, _no_side_tools) -> None:
    from realmock.platform.capabilities.ai.llm.client.base import LLMUpstreamError

    async def fake_run_agent_loop(*a, **k):
        raise LLMUpstreamError("provider down")

    with (
        patch("realmock.domains.growth.agents.insight.LLMClient.from_db", return_value=MagicMock()),
        patch("realmock.domains.growth.agents.insight.run_agent_loop", side_effect=fake_run_agent_loop),
    ):
        assert _run(_generate()) is None


def test_generate_none_on_unexpected_error(_index, _no_side_tools) -> None:
    async def fake_run_agent_loop(*a, **k):
        raise RuntimeError("loop blew up")

    with (
        patch("realmock.domains.growth.agents.insight.LLMClient.from_db", return_value=MagicMock()),
        patch("realmock.domains.growth.agents.insight.run_agent_loop", side_effect=fake_run_agent_loop),
    ):
        assert _run(_generate()) is None
