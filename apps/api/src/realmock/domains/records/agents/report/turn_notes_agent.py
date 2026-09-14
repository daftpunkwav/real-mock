"""Stage 1: per-batch turn-notes ReAct loops.

Each batch of dialogue rounds gets its own agent loop with paged ledger tools
plus resume/profile/GitHub context tools; the loop reads, thinks, verifies,
and finally emits one deep note per turn. Missing turn coverage triggers a
bounded repair pass, then DeepReportAgent._ensure_turn_coverage pads missing turns to keep the schema complete.
"""

from __future__ import annotations

import logging
from typing import Any

from realmock.domains.records.agents.report.finalize import finalize_json
from realmock.domains.records.agents.report.ledger_tools import ledger_tool_specs
from realmock.domains.records.agents.report.prompts import (
    TURN_NOTES_SYSTEM_PROMPT,
    notes_json_schema_text,
    turn_notes_user_message,
)
from realmock.domains.records.agents.report.normalize import normalize_turn_note
from realmock.platform.capabilities.ai.agent import OnAgentEvent as OnEvent
from realmock.platform.capabilities.ai.agent import emit_agent_event
from realmock.platform.capabilities.ai.agent.tools.spec import ToolBundle
from realmock.platform.capabilities.ai.agent.tools import invoke_with_timeout

logger = logging.getLogger(__name__)

BATCH_MAX_ROUNDS = 8
_TOOL_TIMEOUT_SECONDS = 30.0
_REPAIR_MAX_ROUNDS = 3
_REPAIR_MAX_TURNS = 12


async def _invoke_tool(bundle: ToolBundle, name: str, args: dict[str, Any]) -> str:
    """Run one tool; canonical platform timeout/error observation contract."""
    raw, _status = await invoke_with_timeout(
        bundle, name, args, timeout=_TOOL_TIMEOUT_SECONDS
    )
    return raw


async def run_turn_notes_batch(
    llm: Any,
    *,
    ledger: dict[str, Any],
    turn_ids: list[str],
    batch_label: str,
    role: str,
    level: str,
    company: str,
    context_specs: list[Any],
    on_event: OnEvent | None = None,
) -> list[dict[str, Any]]:
    """Run one stage-1 ReAct loop; returns raw note dicts for the batch."""
    bundle = ToolBundle()
    bundle.extend(ledger_tool_specs(ledger, turn_ids=turn_ids))
    bundle.extend(context_specs)

    async def execute(name: str, args: dict[str, Any]) -> str:
        return await _invoke_tool(bundle, name, args)

    async def on_tool(name: str, args: dict[str, Any], result: str, tc_id: str) -> None:
        del tc_id
        await emit_agent_event(on_event, {
            "type": "tool_step",
            "stage": "turn_notes",
            "batch": batch_label,
            "name": name,
            "args": {k: str(v)[:80] for k, v in (args or {}).items()},
            "status": "done",
            "result": str(result)[:400],
        })

    messages = [
        {"role": "system", "content": TURN_NOTES_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": turn_notes_user_message(
                role=role,
                level=level,
                company=company,
                turn_ids=turn_ids,
                batch_label=batch_label,
            ),
        },
    ]
    loop = await _run_loop(llm, messages, bundle.definitions(), execute, on_tool, on_event)
    payload = await finalize_json(
        llm, loop, schema_text=notes_json_schema_text(), purpose="turn notes"
    )
    notes = _extract_notes(payload, turn_ids)

    missing = [tid for tid in turn_ids if tid not in {n.get("turn_id") for n in notes}]
    if missing:
        notes.extend(await _repair_missing(llm, ledger, turn_ids=missing, batch_label=batch_label,
                                           role=role, level=level, company=company,
                                           context_specs=context_specs, on_event=on_event))
    return notes


async def _run_loop(
    llm: Any,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    execute: Any,
    on_tool: Any,
    on_event: OnEvent | None,
    max_rounds: int = BATCH_MAX_ROUNDS,
):
    from realmock.platform.capabilities.ai.agent import run_agent_loop

    async def on_thinking(text: str) -> None:
        if text.strip():
            await emit_agent_event(on_event, {"type": "thinking", "content": text[:600]})

    return await run_agent_loop(
        llm,
        messages,
        tools=tools,
        execute=execute,
        max_rounds=max_rounds,
        max_tools_per_round=4,
        temperature=0.2,
        on_tool=on_tool,
        on_thinking=on_thinking,
        wrap_up_hint={
            "role": "system",
            "content": "Wrap up now: output the final JSON object covering every assigned turn_id. No tool calls.",
        },
    )


def _extract_notes(payload: dict[str, Any] | None, turn_ids: list[str]) -> list[dict[str, Any]]:
    if not payload:
        return []
    raw_notes = payload.get("notes")
    if not isinstance(raw_notes, list):
        raw_notes = [payload] if payload.get("turn_id") else []
    wanted = set(turn_ids)
    notes: list[dict[str, Any]] = []
    for raw in raw_notes:
        note = normalize_turn_note(raw)
        if note is not None and note.turn_id in wanted:
            notes.append(note.model_dump())
    return notes


async def _repair_missing(
    llm: Any,
    ledger: dict[str, Any],
    *,
    turn_ids: list[str],
    batch_label: str,
    role: str,
    level: str,
    company: str,
    context_specs: list[Any],
    on_event: OnEvent | None,
) -> list[dict[str, Any]]:
    """Narrow retry for turns the first pass failed to cover."""
    bounded = turn_ids[:_REPAIR_MAX_TURNS]
    logger.info("turn-notes repair pass for %d missing turn(s) [%s]", len(bounded), batch_label)
    bundle = ToolBundle()
    bundle.extend(ledger_tool_specs(ledger, turn_ids=bounded))
    bundle.extend(context_specs)

    async def execute(name: str, args: dict[str, Any]) -> str:
        return await _invoke_tool(bundle, name, args)

    messages = [
        {"role": "system", "content": TURN_NOTES_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": turn_notes_user_message(
                role=role,
                level=level,
                company=company,
                turn_ids=bounded,
                batch_label=f"{batch_label} repair",
                extra_context="A previous pass missed these turns; cover ONLY these turn ids.",
            ),
        },
    ]
    loop = await _run_loop(
        llm, messages, bundle.definitions(), execute, None, on_event,
        max_rounds=_REPAIR_MAX_ROUNDS,
    )
    payload = await finalize_json(
        llm, loop, schema_text=notes_json_schema_text(), purpose="turn notes repair"
    )
    return _extract_notes(payload, bounded)


__all__ = ["run_turn_notes_batch"]
