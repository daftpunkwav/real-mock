"""Deep report agent: JSON extraction, normalization, ledger tools, two-stage pipeline."""

from __future__ import annotations

import json
from typing import Any

import pytest

from realmock.domains.records.agents.report.agent import (
    DeepReportAgent,
    split_turn_ids,
)
from realmock.domains.records.agents.report.finalize import extract_json_object
from realmock.domains.records.agents.report.ledger_tools import (
    ledger_tool_specs,
    notes_tool_specs,
)
from realmock.domains.records.agents.report.normalize import (
    normalize_report_payload,
    normalize_turn_note,
)


# ---- JSON extraction ------------------------------------------------------------


def test_extract_json_object_plain_fenced_and_noisy():
    payload = {"a": 1, "notes": []}
    assert extract_json_object(json.dumps(payload)) == payload
    assert extract_json_object(f"```json\n{json.dumps(payload)}\n```") == payload
    noisy = f'Here is the report:\n{json.dumps(payload)}\nHope it helps.'
    assert extract_json_object(noisy) == payload
    assert extract_json_object("no json at all") is None
    assert extract_json_object("") is None


# ---- normalization --------------------------------------------------------------


def test_normalize_turn_note_aliases_and_clamps():
    note = normalize_turn_note({
        "turn_id": "t-1",
        "面试官问题": "讲讲缓存穿透",
        "回答摘要": "提到了布隆过滤器",
        "score": "888",
        "problems": ["没提空值缓存", "", 42],
        "参考答案": "先查空值缓存再布隆过滤器",
        "knowledge_points": ["缓存", "布隆过滤器", "Redis"] * 5,
    })
    assert note is not None
    assert note.question == "讲讲缓存穿透"
    assert note.answer_summary == "提到了布隆过滤器"
    assert note.score == 100
    # tolerant coercion: non-string items are stringified, empties dropped
    assert note.problems == ["没提空值缓存", "42"]
    assert note.reference_answer == "先查空值缓存再布隆过滤器"
    assert len(note.knowledge_points) == 8
    assert normalize_turn_note({"no_turn_id": True}) is None
    assert normalize_turn_note("garbage") is None


def test_normalize_turn_note_brushup_and_exercises():
    note = normalize_turn_note({
        "turn_id": "t-2",
        "知识精讲": "布隆过滤器用多个哈希判不存在，而空值缓存直接存 NULL 标记",
        "exercises": ["写出缓存穿透的三种解法及取舍（方向：从成本与误判率对比）", "", 42],
    })
    assert note is not None
    assert "布隆过滤器" in note.knowledge_brushup
    assert note.exercises == ["写出缓存穿透的三种解法及取舍（方向：从成本与误判率对比）", "42"]

    capped = normalize_turn_note({
        "turn_id": "t-3",
        "knowledge_brushup": "x" * 900,
        "exercises": ["e1", "e2", "e3", "e4", "e5"],
    })
    assert capped is not None
    assert len(capped.knowledge_brushup) == 800
    assert len(capped.exercises) == 4


def test_normalize_report_payload_verdict_and_breakdown():
    report = normalize_report_payload({
        "overall_score": "83",
        "score_breakdown": {"technical": 90, "communication": "70.4", "politeness": 999},
        "verdict": "通过",
        "highlights": ["库存项目讲得深"],
        "turn_notes": [
            {"turn_id": "t-1", "score": 80},
            {"turn_id": "t-1", "score": 99},  # deduped
            "garbage",
        ],
    })
    assert report.overall_score == 83
    assert report.score_breakdown.technical == 90
    assert report.score_breakdown.communication == 70
    assert report.score_breakdown.politeness == 100
    assert report.verdict == "passed"
    assert [n.turn_id for n in report.turn_notes] == ["t-1"]


# ---- ledger / notes tools --------------------------------------------------------


def _ledger() -> dict[str, Any]:
    return {
        "schema": "realmock.ledger.v1",
        "frozen": True,
        "turns": [
            {"turn_id": f"t-{i:04d}", "phase": "self_intro" if i < 2 else "project_deep_dive",
             "assistant": {"text": f"问题{i}:讲讲项目"}, "user": {"text": f"回答{i} 涉及缓存"}}
            for i in range(1, 6)
        ],
    }


@pytest.mark.anyio
async def test_ledger_tools_overview_read_search():
    import asyncio

    specs = {s.name: s for s in ledger_tool_specs(_ledger())}
    overview = json.loads(await asyncio.wait_for(specs["ledger_overview"].handler({}), 5))
    assert overview["total_turns"] == 5

    page = json.loads(await asyncio.wait_for(
        specs["ledger_read_turns"].handler({"offset": 0}), 5))
    assert page["returned"] == 5  # fewer than one page
    assert page["next_offset"] is None
    assert page["turns"][0]["question"].startswith("问题1")

    scoped = {s.name: s for s in ledger_tool_specs(_ledger(), turn_ids=["t-0001"])}
    scoped_page = json.loads(await asyncio.wait_for(
        scoped["ledger_read_turns"].handler({}), 5))
    assert scoped_page["total_turns"] == 1

    hits = json.loads(await asyncio.wait_for(
        specs["ledger_search"].handler({"keyword": "缓存"}), 5))
    assert len(hits["matches"]) == 5


@pytest.mark.anyio
async def test_notes_tool_paging():
    import asyncio

    notes = [{"turn_id": f"t-{i}"} for i in range(15)]
    spec = notes_tool_specs(notes)[0]
    page = json.loads(await asyncio.wait_for(spec.handler({"offset": 10}), 5))
    assert page["returned"] == 5
    assert page["next_offset"] is None


# ---- two-stage pipeline ----------------------------------------------------------


class _ScriptedLLM:
    """Per-call scripted payloads for the agent loop's chat_message_stream."""

    def __init__(self, payloads: list[dict[str, Any]]):
        self.payloads = list(payloads)
        self.api_key = "test-key"

    async def chat_message_stream(self, messages, temperature=0.7, tools=None):
        del messages, temperature, tools
        payload = self.payloads.pop(0) if self.payloads else {}
        yield {
            "type": "message",
            "message": {"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)},
        }

    async def chat_json(self, messages, temperature=0.3):
        del messages, temperature
        return self.payloads.pop(0) if self.payloads else {}


@pytest.mark.anyio
async def test_deep_report_agent_two_stage_and_events():
    events: list[dict] = []

    async def _on_event(event: dict) -> None:
        events.append(event)

    notes_payload = {
        "notes": [
            {"turn_id": f"t-{i:04d}", "question": f"q{i}", "score": 70 + i,
             "problems": ["含糊"], "reference_answer": "r", "knowledge_points": ["缓存"]}
            for i in range(1, 6)
        ]
    }
    synthesis_payload = {
        "overall_score": 78,
        "score_breakdown": {"technical": 75, "overall": 78},
        "verdict": "failed",
        "verdict_reasoning": "深度不足",
        "key_problems": ["项目深度不足"],
        "training_plan": ["刷缓存专题"],
    }
    llm = _ScriptedLLM([notes_payload, synthesis_payload])
    agent = DeepReportAgent(llm, on_event=_on_event, context_specs=[])

    report = await agent.run(
        role="Backend", level="junior", company="acme",
        ledger=_ledger(), session_result="failed",
    )

    assert report.verdict == "failed"
    assert report.overall_score == 78
    assert [n.turn_id for n in report.turn_notes] == [f"t-{i:04d}" for i in range(1, 6)]
    # coverage padding fills the turns the stage-1 batch didn't return
    assert all(n.turn_id for n in report.turn_notes)
    assert report.turn_notes[0].score == 71  # 70 + i (i=1)
    assert any(e.get("type") == "stage" and e.get("stage") == "synthesis" for e in events)


def test_split_turn_ids():
    assert split_turn_ids([]) == []
    assert [len(b) for b in split_turn_ids([f"t{i}" for i in range(25)])] == [12, 12, 1]


@pytest.mark.anyio
async def test_coverage_padding_when_synthesis_drops_notes():
    notes_payload = {"notes": [{"turn_id": "t-0001", "score": 50}]}
    synthesis_payload = {"overall_score": 50, "turn_notes": [{"turn_id": "t-0001", "score": 50}]}
    llm = _ScriptedLLM([notes_payload, synthesis_payload])
    agent = DeepReportAgent(llm, context_specs=[])
    report = await agent.run(role="r", level="l", company="c", ledger=_ledger())
    assert [n.turn_id for n in report.turn_notes] == [f"t-{i:04d}" for i in range(1, 6)]


def test_normalize_report_payload_keeps_external_notes():
    payload = {
        "overall_score": 80,
        "external_notes": [
            "ByteDance tech rounds focus on system design trade-offs — confirmed "
            "against https://example.com/byte-interview (fetched).",
            "",  # dropped by clipping
        ],
        "turn_notes": [],
    }
    report = normalize_report_payload(payload)
    assert len(report.external_notes) == 1
    assert "https://example.com/byte-interview" in report.external_notes[0]


def test_synthesis_specs_include_web_tools():
    """Synthesis is the external-calibration loop: web_search + web_fetch present."""
    from realmock.domains.records.agents.report.agent import build_context_specs
    from realmock.platform.capabilities.ai.agent.tools import (
        search_tool_spec,
        web_fetch_tool_spec,
    )

    specs = [*build_context_specs(None, None), search_tool_spec(), web_fetch_tool_spec()]
    names = {s.name for s in specs}
    assert {"web_search", "web_fetch", "github_get_user"} <= names
