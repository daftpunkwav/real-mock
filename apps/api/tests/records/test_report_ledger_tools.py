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
async def test_read_turns_explicit_ids_continue_at_the_first_turn_that_did_not_fit() -> None:
    """A trimmed explicit page must not skip the turns it did not deliver.

    The stage-one note agent asks for the turns of its batch by id. When the
    page is trimmed, the cursor used to step over the delivered window and
    the model never saw the turns in between - the batch was analysed without
    the evidence of those turns.
    """
    from realmock.domains.records.agents.report import ledger_tools as mod

    specs = {s.name: s for s in mod.ledger_tool_specs(_long_ledger(12))}
    asked = [f"t-{i:04d}" for i in range(1, 13)]

    first = json.loads(await specs["ledger_read_turns"].handler({"turn_ids": asked}))
    assert first["truncated"] is True
    # The cursor points at the first turn that did not fit, not past the window.
    assert first["next_offset"] == first["returned"]
    assert first["next_offset"] < len(asked)

    second = json.loads(
        await specs["ledger_read_turns"].handler(
            {"turn_ids": asked, "offset": first["next_offset"]}
        )
    )
    delivered = [turn["turn_id"] for turn in first["turns"]] + [
        turn["turn_id"] for turn in second["turns"]
    ]
    assert delivered == asked[: len(delivered)]
    assert len(set(delivered)) == len(delivered)


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


@pytest.mark.asyncio
async def test_ledger_overview_pages_the_turn_ids() -> None:
    """The overview is a page too: a window of ids plus the continuation cursor.

    Every turn id in one payload pushed a few-hundred-turn session's
    observation over the agent loop's cap, which sliced it into a document
    the model cannot parse.
    """
    from realmock.domains.records.agents.report import ledger_tools as mod

    specs = {s.name: s for s in mod.ledger_tool_specs(_long_ledger(120))}
    first = json.loads(await specs["ledger_overview"].handler({}))
    assert first["total_turns"] == 120
    assert len(first["turn_ids"]) == mod._OVERVIEW_IDS
    assert first["next_offset"] == mod._OVERVIEW_IDS

    collected: list[str] = []
    offset = 0
    while True:
        page = json.loads(await specs["ledger_overview"].handler({"offset": offset}))
        collected.extend(page["turn_ids"])
        if page["next_offset"] is None:
            break
        offset = page["next_offset"]
    assert collected == [f"t-{i:04d}" for i in range(1, 121)]


@pytest.mark.asyncio
async def test_ledger_overview_stays_inside_the_observation_cap() -> None:
    """The overview page is bounded by construction, whatever the ledger holds.

    A degenerate plan can carry very long phase labels and a session can hold
    hundreds of turns; neither may push the observation over the loop cap. A
    label that had to be shortened is reported through ``phases_truncated``.
    """
    from realmock.domains.records.agents.report import ledger_tools as mod

    ledger = _long_ledger(1000)
    ledger["turns"][0]["phase"] = "超长阶段标签" * 1000
    specs = {s.name: s for s in mod.ledger_tool_specs(ledger)}
    raw = await specs["ledger_overview"].handler({})
    assert len(raw) <= mod._OUTPUT_CHARS
    page = json.loads(raw)  # must not raise: the observation is a JSON document
    assert page["phases"][0] != "超长阶段标签" * 1000
    assert mod._json_escaped_chars(page["phases"][0]) <= mod._PHASE_CHARS
    assert page["total_phases"] == 2
    assert page["phases_truncated"] is True


@pytest.mark.asyncio
async def test_ledger_overview_bounds_labels_that_json_escapes() -> None:
    """A phase label is clipped by its serialized length, not its character count.

    ``json.dumps`` expands a control character to a six-character escape, so
    thirty distinct labels that each fit the character cap used to serialize
    past the observation cap; the agent loop then sliced the document open.
    """
    from realmock.domains.records.agents.report import ledger_tools as mod

    ledger = {
        "turns": [
            {"turn_id": f"t-{i:04d}", "phase": f"{i:02d}" + "\x00" * 200}
            for i in range(mod._OVERVIEW_PHASES + 10)
        ]
    }
    specs = {s.name: s for s in mod.ledger_tool_specs(ledger)}
    raw = await specs["ledger_overview"].handler({})
    assert len(raw) <= mod._OUTPUT_CHARS
    page = json.loads(raw)  # must not raise: the observation is a JSON document
    assert len(page["phases"]) == mod._OVERVIEW_PHASES
    # The distinguishing prefix survives clipping (a cleared label would fail).
    assert all(phase.startswith(f"{i:02d}") for i, phase in enumerate(page["phases"]))
    assert all(0 < mod._json_escaped_chars(phase) <= mod._PHASE_CHARS for phase in page["phases"])
    assert page["phases_truncated"] is True


@pytest.mark.asyncio
async def test_ledger_overview_keeps_distinct_phases_that_share_a_prefix() -> None:
    """Labels that differ only after the cap stay distinct in the overview.

    Clipping first collapsed the two labels into one entry; the digest suffix
    keeps them distinguishable after projection.
    """
    from realmock.domains.records.agents.report import ledger_tools as mod

    prefix = "p" * mod._PHASE_CHARS
    ledger = {
        "turns": [
            {"turn_id": "t-0001", "phase": prefix + "alpha"},
            {"turn_id": "t-0002", "phase": prefix + "beta"},
        ]
    }
    specs = {s.name: s for s in mod.ledger_tool_specs(ledger)}
    page = json.loads(await specs["ledger_overview"].handler({}))
    assert len(page["phases"]) == 2
    assert page["phases"][0] != page["phases"][1]
    assert all(phase.startswith(prefix[: mod._PHASE_CHARS - 9]) for phase in page["phases"])
    assert all(mod._json_escaped_chars(phase) <= mod._PHASE_CHARS for phase in page["phases"])


@pytest.mark.asyncio
async def test_ledger_overview_pages_long_turn_ids_without_slicing_json() -> None:
    """Long preserved turn ids page as bounded handles, never as sliced JSON.

    A legacy payload can hold ids far longer than the usual ``t-0001``; each
    page must stay inside the cap, and every advertised handle must resolve
    its turn through ``ledger_read_turns``.
    """
    from realmock.domains.records.agents.report import ledger_tools as mod

    ids = [f"t-{i:04d}-" + "x" * 400 for i in range(1, 121)]
    ledger = {"turns": [{"turn_id": turn_id, "phase": "tech"} for turn_id in ids]}
    specs = {s.name: s for s in mod.ledger_tool_specs(ledger)}

    collected: list[str] = []
    offset: int | None = 0
    while offset is not None:
        raw = await specs["ledger_overview"].handler({"offset": offset})
        assert len(raw) <= mod._OUTPUT_CHARS
        page = json.loads(raw)  # must not raise: the observation is a JSON document
        assert page["next_offset"] is None or page["next_offset"] > offset
        assert all(
            0 < mod._json_escaped_chars(turn_id) <= mod._TURN_ID_CHARS
            for turn_id in page["turn_ids"]
        )
        collected.extend(page["turn_ids"])
        offset = page["next_offset"]
    # Every turn is advertised exactly once, with a distinct handle.
    assert len(collected) == len(ids)
    assert len(set(collected)) == len(collected)

    page = json.loads(await specs["ledger_read_turns"].handler({"turn_ids": [collected[0]]}))
    assert page["returned"] == 1
    assert page["turns"][0]["turn_id"] == collected[0]


@pytest.mark.asyncio
async def test_ledger_overview_advertises_a_retrievable_handle_for_a_huge_id() -> None:
    """An id too long for a page is advertised as a handle that resolves the turn.

    The overview used to clip the id to a bare prefix that ``ledger_read_turns``
    could not match, so the turn it named was unreachable; the handle projects
    back to the same full id on both sides.
    """
    from realmock.domains.records.agents.report import ledger_tools as mod

    huge = "x" * (mod._OUTPUT_CHARS * 2)
    ledger = {
        "turns": [
            {"turn_id": huge, "phase": "tech", "assistant": {"text": "question"}},
            {"turn_id": "t-0002", "phase": "tech"},
        ]
    }
    specs = {s.name: s for s in mod.ledger_tool_specs(ledger)}

    raw = await specs["ledger_overview"].handler({})
    assert len(raw) <= mod._OUTPUT_CHARS
    page = json.loads(raw)  # must not raise: the observation is a JSON document
    handle = page["turn_ids"][0]
    assert handle  # a cleared placeholder would be unusable
    assert huge.startswith(handle[:-9])  # clipped prefix, then "…" + digest
    assert "…" in handle
    assert mod._bounded_handle(handle, mod._TURN_ID_CHARS) == handle
    assert page["next_offset"] is None

    found = json.loads(await specs["ledger_read_turns"].handler({"turn_ids": [handle]}))
    assert found["returned"] == 1
    assert found["turns"][0]["turn_id"] == handle
    assert found["turns"][0]["question"] == "question"

    rest = json.loads(await specs["ledger_overview"].handler({"offset": 1}))
    assert rest["turn_ids"] == ["t-0002"]
    assert rest["next_offset"] is None


@pytest.mark.asyncio
async def test_ledger_overview_reports_a_clipped_phase_label() -> None:
    """The overview says when it shortened a phase label.

    The shortened label keeps its distinguishing prefix plus a digest, and the
    full label stays readable from a turn page, so the synthesis agent can
    resolve which phase the overview meant.
    """
    from realmock.domains.records.agents.report import ledger_tools as mod

    phase = "phase-" + "y" * 500
    ledger = {"turns": [{"turn_id": "t-0001", "phase": phase}]}
    specs = {s.name: s for s in mod.ledger_tool_specs(ledger)}

    page = json.loads(await specs["ledger_overview"].handler({}))
    assert page["total_phases"] == 1
    assert page["phases_truncated"] is True
    assert page["phases"][0] != phase
    assert page["phases"][0].startswith(phase[: mod._PHASE_CHARS - 9])

    turn_page = json.loads(await specs["ledger_read_turns"].handler({"offset": 0}))
    assert turn_page["turns"][0]["phase"] == phase


@pytest.mark.asyncio
async def test_ledger_overview_reports_phases_beyond_the_page() -> None:
    """A phase list longer than the page is reported, not silently cut."""
    from realmock.domains.records.agents.report import ledger_tools as mod

    ledger = {"turns": [{"turn_id": f"t-{i:04d}", "phase": f"phase-{i:02d}"} for i in range(40)]}
    specs = {s.name: s for s in mod.ledger_tool_specs(ledger)}
    page = json.loads(await specs["ledger_overview"].handler({}))
    assert len(page["phases"]) == mod._OVERVIEW_PHASES
    assert page["total_phases"] == 40
    assert page["phases_truncated"] is True


@pytest.mark.asyncio
async def test_ledger_overview_worst_case_payload_stays_inside_the_cap() -> None:
    """The projections keep the page inside the cap at the caps' own limits.

    30 escaped labels and 50 legacy-length ids are the largest overview a
    ledger can produce; the serialized page still fits the loop cap with the
    cursor fields on top.
    """
    from realmock.domains.records.agents.report import ledger_tools as mod

    turns = []
    for i in range(50):
        turn_id = f"t-{i:04d}-" + "x" * 500
        phase = f"{i:02d}" + "\x00" * 200 if i < mod._OVERVIEW_PHASES else "tech"
        turns.append({"turn_id": turn_id, "phase": phase})
    specs = {s.name: s for s in mod.ledger_tool_specs({"turns": turns})}

    raw = await specs["ledger_overview"].handler({})
    assert len(raw) <= mod._OUTPUT_CHARS
    page = json.loads(raw)  # must not raise: the observation is a JSON document
    assert len(page["phases"]) == mod._OVERVIEW_PHASES
    assert len(page["turn_ids"]) == 50
    assert all(mod._json_escaped_chars(phase) <= mod._PHASE_CHARS for phase in page["phases"])
    assert all(
        mod._json_escaped_chars(turn_id) <= mod._TURN_ID_CHARS for turn_id in page["turn_ids"]
    )


@pytest.mark.asyncio
async def test_ledger_overview_projects_an_escaped_id_at_a_later_page() -> None:
    """An escaped id anywhere in the ledger becomes a handle, not a broken page.

    A control-character id is far longer once serialized than its character
    count suggests, and it can sit past the first page boundary; every page
    stays bounded and the cursor neither skips nor repeats it.
    """
    from realmock.domains.records.agents.report import ledger_tools as mod

    turns = [
        {
            "turn_id": "\x00" * 3_000 if i == 59 else f"t-{i + 1:04d}",
            "phase": "tech",
            "assistant": {"text": f"question {i + 1}"},
        }
        for i in range(120)
    ]
    specs = {s.name: s for s in mod.ledger_tool_specs({"turns": turns})}

    collected: list[str] = []
    offset: int | None = 0
    while offset is not None:
        raw = await specs["ledger_overview"].handler({"offset": offset})
        assert len(raw) <= mod._OUTPUT_CHARS
        page = json.loads(raw)  # must not raise: the observation is a JSON document
        assert page["next_offset"] is None or page["next_offset"] > offset
        assert all(0 < mod._json_escaped_chars(turn_id) for turn_id in page["turn_ids"])
        assert all(
            mod._json_escaped_chars(turn_id) <= mod._TURN_ID_CHARS for turn_id in page["turn_ids"]
        )
        collected.extend(page["turn_ids"])
        offset = page["next_offset"]

    assert len(collected) == 120
    escaped_handle = collected[59]
    assert escaped_handle
    found = json.loads(await specs["ledger_read_turns"].handler({"turn_ids": [escaped_handle]}))
    assert found["returned"] == 1
    assert found["turns"][0]["turn_id"] == escaped_handle
    assert found["turns"][0]["question"] == "question 60"


@pytest.mark.asyncio
async def test_ledger_overview_clamps_an_oversized_offset() -> None:
    """A huge model-supplied offset must not inflate the serialized page.

    The offset is echoed in the payload, so an unbounded integer would fail
    serialization (an integer of more than 4,300 digits cannot be turned back
    into text) regardless of how few ids the page carries.
    """
    from realmock.domains.records.agents.report import ledger_tools as mod

    specs = {s.name: s for s in mod.ledger_tool_specs(_long_ledger(120))}
    raw = await specs["ledger_overview"].handler({"offset": 10**mod._OUTPUT_CHARS})
    assert len(raw) <= mod._OUTPUT_CHARS
    page = json.loads(raw)  # must not raise: the observation is a JSON document
    assert page["offset"] == 120
    assert page["turn_ids"] == []
    assert page["next_offset"] is None


@pytest.mark.asyncio
async def test_ledger_read_turns_single_entry_fits_with_legacy_fields() -> None:
    """One projected turn always fits the loop cap, whatever the ledger holds.

    A legacy turn can carry an arbitrarily long id, phase label or text. The
    projection bounds every field, so ``_fit_page`` never keeps a single entry
    that the agent loop would slice into an unparsable document.
    """
    from realmock.domains.records.agents.report import ledger_tools as mod
    from realmock.platform.capabilities.ai.agent.llm_round import (
        MAX_TOOL_RESULT_CHARS,
        _truncate_tool_result,
    )

    ledger = {
        "turns": [
            {
                "turn_id": "t-" + "\x00" * 30_000,
                "phase": "\x00" * 30_000,
                "assistant": {"text": "\x00" * 5_000},
                "user": {"text": "\x00" * 5_000},
                "tools": [
                    {"name": "\x00" * 5_000, "result_preview": "\x00" * 5_000}
                    for _ in range(mod._TOOLS_PER_TURN)
                ],
            }
        ]
    }
    specs = {s.name: s for s in mod.ledger_tool_specs(ledger)}
    raw = await specs["ledger_read_turns"].handler({"offset": 0})
    assert len(raw) <= MAX_TOOL_RESULT_CHARS
    assert _truncate_tool_result(raw) == raw
    page = json.loads(raw)  # must not raise: the observation is a JSON document
    assert page["returned"] == 1
    assert page["turns"][0]["turn_id"]


@pytest.mark.asyncio
async def test_ledger_search_projects_long_ids_and_snippets() -> None:
    """Search hits stay bounded: ids are handles and snippets are clipped."""
    from realmock.domains.records.agents.report import ledger_tools as mod

    ledger = _long_ledger(12)
    for i, turn in enumerate(ledger["turns"], start=1):
        turn["turn_id"] = f"t-{i:04d}-" + "x" * 400
        turn["assistant"]["text"] = "\x00" * 1_000 + " keyword"
    specs = {s.name: s for s in mod.ledger_tool_specs(ledger)}
    raw = await specs["ledger_search"].handler({"keyword": "keyword"})
    assert len(raw) <= mod._OUTPUT_CHARS
    page = json.loads(raw)  # must not raise: the observation is a JSON document
    assert 0 < len(page["matches"]) <= mod._SEARCH_HITS
    assert all(
        0 < mod._json_escaped_chars(hit["turn_id"]) <= mod._TURN_ID_CHARS for hit in page["matches"]
    )
    assert all(
        0 < mod._json_escaped_chars(hit["snippet"]) <= mod._SNIPPET_CHARS for hit in page["matches"]
    )
