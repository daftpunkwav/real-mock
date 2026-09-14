"""Ledger reading tools for the ReAct report agents (progressive disclosure).

The frozen transcript is never dumped into the prompt in one shot: agents
pull it in bounded pages through ``ledger_overview`` / ``ledger_read_turns`` /
``ledger_search``. A batch run scopes reads to its own turn range.
"""

from __future__ import annotations

import json
from typing import Any

from realmock.platform.capabilities.ai.agent.tools.spec import ToolSpec

_PAGE_TURNS = 12
_TURN_CHARS = 900
_SEARCH_HITS = 8
_SNIPPET_CHARS = 240
_OUTPUT_CHARS = 14_000


def _turns(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    turns = ledger.get("turns")
    if not isinstance(turns, list):
        return []
    return [t for t in turns if isinstance(t, dict)]


def _turn_text(turn: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("assistant", "user"):
        val = turn.get(key)
        if isinstance(val, dict):
            parts.append(str(val.get("text", "")))
        elif val:
            parts.append(str(val))
    return " ".join(parts).lower()


def _project_turn(turn: dict[str, Any]) -> dict[str, Any]:
    assistant = turn.get("assistant") or {}
    user = turn.get("user") or {}
    tools = turn.get("tools") or []
    return {
        "turn_id": turn.get("turn_id"),
        "phase": turn.get("phase"),
        "question": str(assistant.get("text", ""))[:_TURN_CHARS] if isinstance(assistant, dict) else "",
        "answer": str(user.get("text", ""))[:_TURN_CHARS] if isinstance(user, dict) else "",
        "tools": [
            {"name": t.get("name"), "preview": str(t.get("result", ""))[:200]}
            for t in tools[:4]
            if isinstance(t, dict)
        ],
    }


def ledger_tool_specs(
    ledger: dict[str, Any],
    *,
    turn_ids: list[str] | None = None,
) -> list[ToolSpec]:
    """Build ledger tools; optionally scoped to ``turn_ids`` (one batch).

    With a scope, ``ledger_read_turns`` pages within the scope only and
    ``ledger_overview`` reports the scope, keeping each batch agent focused.
    """
    allowed: set[str] | None = set(turn_ids) if turn_ids is not None else None
    scoped = [t for t in _turns(ledger) if allowed is None or str(t.get("turn_id")) in allowed]

    async def overview(_args: dict[str, Any]) -> str:
        phases: list[str] = []
        for turn in scoped:
            phase = str(turn.get("phase") or "")
            if phase and phase not in phases:
                phases.append(phase)
        return json.dumps(
            {
                "total_turns": len(scoped),
                "phases": phases[:30],
                "turn_ids": [str(t.get("turn_id")) for t in scoped],
            },
            ensure_ascii=False,
        )

    async def read_turns(args: dict[str, Any]) -> str:
        offset = max(0, int(args.get("offset") or 0))
        requested = args.get("turn_ids")
        if isinstance(requested, list) and requested:
            want = {str(t) for t in requested[:_PAGE_TURNS * 2]}
            page = [t for t in scoped if str(t.get("turn_id")) in want]
        else:
            page = scoped[offset : offset + _PAGE_TURNS]
        payload = {
            "offset": offset,
            "returned": len(page),
            "total_turns": len(scoped),
            "next_offset": offset + _PAGE_TURNS if offset + _PAGE_TURNS < len(scoped) else None,
            "turns": [_project_turn(t) for t in page],
        }
        raw = json.dumps(payload, ensure_ascii=False)
        return raw[:_OUTPUT_CHARS]

    async def search(args: dict[str, Any]) -> str:
        keyword = str(args.get("keyword") or "").strip().lower()
        if not keyword:
            return json.dumps({"error": "empty_keyword"}, ensure_ascii=False)
        hits = []
        for turn in scoped:
            text = _turn_text(turn)
            if keyword in text:
                idx = text.find(keyword)
                snippet = text[max(0, idx - 40) : idx + _SNIPPET_CHARS]
                hits.append({"turn_id": turn.get("turn_id"), "snippet": snippet})
            if len(hits) >= _SEARCH_HITS:
                break
        return json.dumps({"matches": hits}, ensure_ascii=False)

    return [
        ToolSpec(
            name="ledger_overview",
            description="Overview of the frozen interview transcript: turn count, phase list, ordered turn ids.",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=overview,
        ),
        ToolSpec(
            name="ledger_read_turns",
            description=(
                "Read transcript turns by page (offset-based) or by explicit turn_ids; "
                "each turn carries the interviewer question, the candidate answer, and tool previews."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "offset": {"type": "integer", "description": "Page offset (0-based); default 0"},
                    "turn_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Explicit turn ids to fetch (overrides offset)",
                    },
                },
                "required": [],
            },
            handler=read_turns,
        ),
        ToolSpec(
            name="ledger_search",
            description="Keyword-search the transcript; returns matching turn ids with short snippets.",
            parameters={
                "type": "object",
                "properties": {"keyword": {"type": "string"}},
                "required": ["keyword"],
            },
            handler=search,
        ),
    ]


def notes_tool_specs(notes: list[dict[str, Any]]) -> list[ToolSpec]:
    """Paged access to the accumulated per-turn notes (synthesis stage)."""

    async def read_notes(args: dict[str, Any]) -> str:
        offset = max(0, int(args.get("offset") or 0))
        limit = max(1, min(int(args.get("limit") or 10), 20))
        page = notes[offset : offset + limit]
        return json.dumps(
            {
                "offset": offset,
                "returned": len(page),
                "total": len(notes),
                "next_offset": offset + len(page) if offset + len(page) < len(notes) else None,
                "notes": page,
            },
            ensure_ascii=False,
        )[:_OUTPUT_CHARS]

    return [
        ToolSpec(
            name="report_read_notes",
            description="Read the per-turn analysis notes produced in stage 1 (paged).",
            parameters={
                "type": "object",
                "properties": {
                    "offset": {"type": "integer"},
                    "limit": {"type": "integer", "description": "Max notes per page (default 10)"},
                },
                "required": [],
            },
            handler=read_notes,
        ),
    ]


__all__ = ["ledger_tool_specs", "notes_tool_specs"]
