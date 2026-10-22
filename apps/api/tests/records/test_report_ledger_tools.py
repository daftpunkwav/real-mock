"""Ledger-tool tests for realmock.domains.records.agents.report.ledger_tools.

Covers: _turns/_turn_text edges, ledger_read_turns/ledger_search handlers,
and the tool preview projection (the tool result must reach the page)
Conventions: Pure in-memory ledger; no LLM/DB; rate limits reset per test
"""

from __future__ import annotations

import json

import pytest

from realmock.domains.interview.ledger.store import build_tool_preview
from realmock.platform.core.ratelimit import reset_rate_limit


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()


@pytest.mark.asyncio
async def test_ledger_gaps() -> None:
    from realmock.domains.records.agents.report import ledger_tools as mod

    assert mod._turns({}) == []
    assert mod._turns({"turns": "bad"}) == []
    assert "hi" in mod._turn_text({"assistant": "hi string", "user": None})
    ledger = {
        "turns": [
            {
                "turn_id": f"t-{i:04d}",
                "phase": "tech",
                "assistant": {"text": f"q{i} keyword"},
                "user": {"text": f"a{i}"},
                "tools": [],
            }
            for i in range(10)
        ]
    }
    specs = {s.name: s for s in mod.ledger_tool_specs(ledger)}
    out = json.loads(await specs["ledger_read_turns"].handler({"turn_ids": ["t-0001"]}))
    assert out["returned"] == 1
    empty = json.loads(await specs["ledger_search"].handler({"keyword": ""}))
    assert empty["error"] == "empty_keyword"
    many = json.loads(await specs["ledger_search"].handler({"keyword": "keyword"}))
    assert len(many["matches"]) <= 8


def _long_ledger(count: int) -> dict:
    """A ledger whose turns exceed the tool output budget when read as one page."""
    return {
        "turns": [
            {
                "turn_id": f"t-{i:04d}",
                "phase": "project_deep_dive",
                "assistant": {"text": "请详细描述你在项目中负责的核心模块架构与技术取舍。" * 8},
                "user": {"text": "我负责了订单履约链路的设计，并用 Kafka 实现异步解耦。" * 8},
                "tools": [
                    build_tool_preview("web_search", {"q": "kafka"}, "x" * 200) for _ in range(4)
                ],
            }
            for i in range(1, count + 1)
        ]
    }


@pytest.mark.asyncio
async def test_read_turns_carries_the_tool_result_text() -> None:
    """The page must carry the result the interviewer-side tool call returned.

    The ledger writer stores a tool preview under ``result_preview``; a reader
    that looks up another key loses the tool output silently, so the report
    can no longer cite what the tool returned.
    """
    from realmock.domains.records.agents.report import ledger_tools as mod

    preview = build_tool_preview("web_search", {"q": "kafka"}, "Kafka 保证同一分区内消息顺序")
    # The writer's real shape: the result text lives under result_preview.
    assert set(preview) == {"name", "args_preview", "result_preview", "ok", "chars"}
    ledger = {
        "turns": [
            {
                "turn_id": "t-0001",
                "phase": "tech",
                "assistant": {"text": "Kafka 如何保证顺序？", "visible": True},
                "user": {"text": "靠分区键", "source": "text"},
                "tools": [preview],
            }
        ]
    }
    specs = {s.name: s for s in mod.ledger_tool_specs(ledger)}
    page = json.loads(await specs["ledger_read_turns"].handler({"offset": 0}))
    assert page["turns"][0]["tools"] == [
        {"name": "web_search", "preview": "Kafka 保证同一分区内消息顺序"}
    ]


@pytest.mark.asyncio
async def test_read_turns_tolerates_a_tool_preview_without_a_result() -> None:
    """A preview without the result key still projects (no crash, no text)."""
    from realmock.domains.records.agents.report import ledger_tools as mod

    ledger = {
        "turns": [
            {
                "turn_id": "t-0001",
                "phase": "tech",
                "assistant": {"text": "q", "visible": True},
                "tools": [{"name": "web_search"}],
            }
        ]
    }
    specs = {s.name: s for s in mod.ledger_tool_specs(ledger)}
    page = json.loads(await specs["ledger_read_turns"].handler({"offset": 0}))
    assert page["turns"][0]["tools"] == [{"name": "web_search", "preview": ""}]


@pytest.mark.asyncio
async def test_read_turns_page_stays_valid_json() -> None:
    """A full page of long turns must be trimmed, not sliced into invalid JSON."""
    from realmock.domains.records.agents.report import ledger_tools as mod

    specs = {s.name: s for s in mod.ledger_tool_specs(_long_ledger(12))}
    raw = await specs["ledger_read_turns"].handler({"offset": 0})
    page = json.loads(raw)  # must not raise: the observation is a JSON document
    assert len(raw) <= mod._OUTPUT_CHARS
    assert page["returned"] == len(page["turns"])
    assert page["truncated"] is True
    # The continuation cursor points at the first turn that did not fit.
    assert page["next_offset"] == page["returned"]
    assert page["total_turns"] == 12


@pytest.mark.asyncio
async def test_read_turns_page_survives_the_agent_loop_observation_cap() -> None:
    """A fitted page must reach the model as valid JSON.

    The agent loop slices any tool observation longer than its cap, which cuts
    inside the serialized page and hands the model an unparsable document. The
    page budget therefore has to stay at or below that cap: a page that fits
    the tool budget but exceeds the loop cap is still cut on the way to the
    model, which is exactly the failure the page fitter exists to prevent.
    """
    from realmock.domains.records.agents.report import ledger_tools as mod
    from realmock.platform.capabilities.ai.agent.llm_round import (
        MAX_TOOL_RESULT_CHARS,
        _truncate_tool_result,
    )

    specs = {s.name: s for s in mod.ledger_tool_specs(_long_ledger(12))}
    raw = await specs["ledger_read_turns"].handler({"offset": 0})
    assert len(raw) <= MAX_TOOL_RESULT_CHARS
    # The loop must hand the page over untouched.
    assert _truncate_tool_result(raw) == raw
    page = json.loads(raw)  # must not raise
    assert page["truncated"] is True


@pytest.mark.asyncio
async def test_read_turns_short_page_is_not_marked_truncated() -> None:
    """A page that fits the budget is returned whole and is not flagged."""
    from realmock.domains.records.agents.report import ledger_tools as mod

    specs = {s.name: s for s in mod.ledger_tool_specs(_long_ledger(3))}
    page = json.loads(await specs["ledger_read_turns"].handler({"offset": 0}))
    assert page["returned"] == 3
    assert "truncated" not in page
    assert page["next_offset"] is None


@pytest.mark.asyncio
async def test_read_notes_page_stays_valid_json() -> None:
    """The synthesis notes reader must also stay valid JSON when a page is large."""
    from realmock.domains.records.agents.report import ledger_tools as mod
    from realmock.domains.records.agents.report.normalize import normalize_turn_note

    # The real stage-1 output shape: a normalized turn note (clipped fields).
    note = normalize_turn_note(
        {
            "turn_id": "t-0001",
            "question": "请详细描述你在项目中的核心贡献。" * 8,
            "question_intent": "考察架构能力" * 10,
            "answer_summary": "我负责了订单履约链路。" * 20,
            "reference_answer": "参考回答：先讲背景再讲动作最后讲结果。" * 12,
            "how_to_answer": "先给结论再给论据。" * 10,
            "knowledge_brushup": "补充 Kafka 事务语义。" * 6,
            "followup_quality": "追问后补充了细节。" * 6,
            "problems": ["缺少量化指标"] * 6,
            "knowledge_points": ["分布式事务"] * 8,
            "exercises": ["复述一遍 Kafka 语义"] * 4,
        }
    )
    assert note is not None
    notes = [dict(note.model_dump(), turn_id=f"t-{i:04d}") for i in range(1, 11)]
    raw = await mod.notes_tool_specs(notes)[0].handler({"offset": 0})
    page = json.loads(raw)  # must not raise
    assert len(raw) <= mod._OUTPUT_CHARS
    assert page["returned"] == len(page["notes"])
    assert page["truncated"] is True
    assert page["next_offset"] == page["returned"]


@pytest.mark.asyncio
async def test_read_notes_page_survives_the_agent_loop_observation_cap() -> None:
    """The synthesis notes reader must survive the agent loop's observation cap.

    The report domain does not compress tool observations, so the loop slices
    anything longer than its cap; a notes page over that cap would reach the
    model as an unparsable document.
    """
    from realmock.domains.records.agents.report import ledger_tools as mod
    from realmock.platform.capabilities.ai.agent.llm_round import (
        MAX_TOOL_RESULT_CHARS,
        _truncate_tool_result,
    )

    notes = [
        {"turn_id": f"t-{i:04d}", "question": "问" * 900, "answer": "答" * 900}
        for i in range(1, 13)
    ]
    raw = await mod.notes_tool_specs(notes)[0].handler({"offset": 0})
    assert len(raw) <= MAX_TOOL_RESULT_CHARS
    assert _truncate_tool_result(raw) == raw
    page = json.loads(raw)  # must not raise
    assert page["truncated"] is True


@pytest.mark.asyncio
async def test_read_turns_degrades_non_numeric_paging_args() -> None:
    """A non-numeric offset must degrade to the first page, not fail the call.

    Malformed paging arguments are a model mistake; the sibling readers (resume
    raw text, memory index, web search) degrade to their default instead of
    raising, so one bad argument must not cost the report agent a round.
    """
    from realmock.domains.records.agents.report import ledger_tools as mod

    specs = {s.name: s for s in mod.ledger_tool_specs(_long_ledger(3))}
    page = json.loads(await specs["ledger_read_turns"].handler({"offset": "next"}))
    assert page["offset"] == 0
    assert page["returned"] == 3
    assert page["next_offset"] is None


@pytest.mark.asyncio
async def test_read_turns_degrades_non_finite_paging_args() -> None:
    """A non-finite offset must degrade too: int(float('inf')) raises OverflowError.

    ``json.loads`` accepts ``Infinity`` (and ``1e400``), so a model answer can
    carry ``inf``; OverflowError is not a ValueError and would escape a
    ``(TypeError, ValueError)`` guard.
    """
    from realmock.domains.records.agents.report import ledger_tools as mod

    specs = {s.name: s for s in mod.ledger_tool_specs(_long_ledger(3))}
    page = json.loads(await specs["ledger_read_turns"].handler({"offset": float("inf")}))
    assert page["offset"] == 0
    assert page["returned"] == 3


@pytest.mark.asyncio
async def test_read_notes_degrades_non_numeric_paging_args() -> None:
    """A non-numeric offset/limit must degrade to the default page, not fail."""
    from realmock.domains.records.agents.report import ledger_tools as mod

    notes = [{"turn_id": f"t-{i:04d}", "question": "q" * 50} for i in range(1, 13)]
    page = json.loads(await mod.notes_tool_specs(notes)[0].handler({"offset": "x", "limit": "y"}))
    assert page["offset"] == 0
    assert page["returned"] == 10
    assert page["next_offset"] == 10


@pytest.mark.asyncio
async def test_read_notes_degrades_non_finite_paging_args() -> None:
    """A non-finite offset/limit must degrade to the default page, not fail."""
    from realmock.domains.records.agents.report import ledger_tools as mod

    notes = [{"turn_id": f"t-{i:04d}", "question": "q" * 50} for i in range(1, 13)]
    page = json.loads(
        await mod.notes_tool_specs(notes)[0].handler(
            {"offset": float("inf"), "limit": float("inf")}
        )
    )
    assert page["offset"] == 0
    assert page["returned"] == 10
    assert page["next_offset"] == 10


@pytest.mark.asyncio
async def test_read_notes_clips_one_oversized_note_so_the_page_fits_the_cap() -> None:
    """A single note larger than the budget is clipped and kept, so paging moves on.

    Dropping it would leave an empty page whose next_offset equals the current
    offset, and the agent would re-read the same page forever. Keeping it
    untrimmed would hand the agent loop an observation longer than its cap,
    and the loop would slice that observation into an unparsable document.
    """
    from realmock.domains.records.agents.report import ledger_tools as mod
    from realmock.domains.records.agents.report.normalize import normalize_turn_note
    from realmock.platform.capabilities.ai.agent.llm_round import (
        MAX_TOOL_RESULT_CHARS,
        _truncate_tool_result,
    )

    # A note whose every field sits at its clip limit: one note can exceed the
    # output budget on its own.
    note = normalize_turn_note(
        {
            "turn_id": "t-0001",
            "phase": "p" * 60,
            "question": "问" * 800,
            "question_intent": "意" * 400,
            "answer_summary": "答" * 1200,
            "problems": ["问" * 400] * 6,
            "reference_answer": "参" * 2000,
            "how_to_answer": "法" * 800,
            "knowledge_points": ["知" * 400] * 8,
            "knowledge_brushup": "补" * 800,
            "exercises": ["练" * 400] * 4,
            "followup_quality": "追" * 400,
            "user_review": {"summary": "用" * 800, "suggestions": ["建" * 400] * 4},
            "interviewer_review": {"intent": "面" * 400, "quality": "q" * 40, "notes": "评" * 400},
        }
    )
    assert note is not None
    notes = [dict(note.model_dump()), dict(note.model_dump(), turn_id="t-0002")]
    raw = await mod.notes_tool_specs(notes)[0].handler({"offset": 0})
    # The page reaches the model whole: the agent loop does not slice it.
    assert len(raw) <= MAX_TOOL_RESULT_CHARS
    assert _truncate_tool_result(raw) == raw
    page = json.loads(raw)  # must not raise
    # One note fits the page; the second one waits for the next page.
    assert page["returned"] == 1
    assert page["notes"][0]["turn_id"] == "t-0001"
    # The note is shortened, not dropped, and the model is told about it.
    assert page["notes"][0]["clipped"] is True
    assert len(page["notes"][0]["reference_answer"]) < len(note.reference_answer or "")
    assert page["truncated"] is True
    # The cursor advances past the entry that was returned.
    assert page["next_offset"] == 1
