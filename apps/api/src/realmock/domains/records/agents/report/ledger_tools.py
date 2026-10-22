"""Ledger reading tools for the ReAct report agents (progressive disclosure).

The frozen transcript is never dumped into the prompt in one shot: agents
pull it in bounded pages through ``ledger_overview`` / ``ledger_read_turns`` /
``ledger_search``. A batch run scopes reads to its own turn range.

Every reader returns a JSON document: a page is trimmed to the output budget
by dropping trailing entries (never by slicing the serialized text, which
would cut inside a string and hand the model an unparsable page). A trimmed
page carries ``truncated: true`` and the continuation cursor. The budget is
the agent loop's own observation cap, so a fitted page reaches the model
whole instead of being sliced there.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from realmock.platform.capabilities.ai.agent.tools.spec import ToolSpec
from realmock.platform.capabilities.ai.llm.defaults import TOOL_OBSERVATION_SOFT_CHARS

_PAGE_TURNS = 12
_TURN_CHARS = 900
_SEARCH_HITS = 8
_SNIPPET_CHARS = 240
#: Serialized page budget.
#:
#: The agent loop hands a tool observation longer than
#: ``TOOL_OBSERVATION_SOFT_CHARS`` to the model sliced at that mark, which cuts
#: inside the serialized page and delivers an unparsable document. The budget
#: is therefore the loop's own cap: a fitted page must reach the model whole,
#: so a private number that can drift above that cap does not belong here.
_OUTPUT_CHARS = TOOL_OBSERVATION_SOFT_CHARS


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
        "question": str(assistant.get("text", ""))[:_TURN_CHARS]
        if isinstance(assistant, dict)
        else "",
        "answer": str(user.get("text", ""))[:_TURN_CHARS] if isinstance(user, dict) else "",
        "tools": [
            {"name": t.get("name"), "preview": str(t.get("result", ""))[:200]}
            for t in tools[:4]
            if isinstance(t, dict)
        ],
    }


def _next_offset(offset: int, returned: int, total: int, *, explicit: bool) -> int | None:
    """Offset cursor for the next page (None at the end of the transcript).

    Offset paging resumes where the current page stopped. An explicit
    ``turn_ids`` request has no cursor of its own, so the offset cursor stays
    the paging hint the model can fall back to.
    """
    consumed = _PAGE_TURNS if explicit else returned
    return offset + consumed if offset + consumed < total else None


def _fit_page(entries: list[Any], payload_for: Callable[[list[Any]], dict[str, Any]]) -> str:
    """Serialize one page of entries as JSON that fits the output budget.

    The observation must stay parsable: slicing the serialized text cuts
    inside a string and hands the model an unparsable page. Trailing entries
    are dropped instead, and the page is marked ``truncated`` so the model
    knows to keep reading. One entry is always kept, so the paging cursor
    advances even when a single entry alone exceeds the budget.
    """
    page = list(entries)
    while True:
        payload = payload_for(page)
        if len(page) < len(entries):
            payload["truncated"] = True
        raw = json.dumps(payload, ensure_ascii=False)
        if len(raw) <= _OUTPUT_CHARS or len(page) <= 1:
            return raw
        page.pop()


def _page_offset(args: dict[str, Any], default: int = 0) -> int:
    """Page offset from model-supplied args; a non-numeric value degrades to the start.

    Malformed paging arguments are a model mistake, not a broken tool: the
    other readers (resume raw text, memory index, web search) degrade to their
    default instead of raising, so one bad argument must not fail the call and
    cost the agent a round. A non-finite value (Infinity) counts as malformed
    too: converting it to int raises OverflowError, which is not a ValueError.
    """
    try:
        return max(0, int(args.get("offset") or default))
    except (TypeError, ValueError, OverflowError):
        return max(0, default)


def _page_limit(args: dict[str, Any], default: int, maximum: int) -> int:
    """Page size from model-supplied args; a non-numeric value degrades to the default."""
    try:
        limit = int(args.get("limit") or default)
    except (TypeError, ValueError, OverflowError):
        limit = default
    return max(1, min(limit, maximum))


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
        offset = _page_offset(args)
        requested = args.get("turn_ids")
        explicit_ids = requested if isinstance(requested, list) and requested else None
        if explicit_ids is not None:
            want = {str(t) for t in explicit_ids[: _PAGE_TURNS * 2]}
            candidates = [t for t in scoped if str(t.get("turn_id")) in want]
        else:
            candidates = scoped[offset : offset + _PAGE_TURNS]
        projected = [_project_turn(t) for t in candidates]
        return _fit_page(
            projected,
            lambda page: {
                "offset": offset,
                "returned": len(page),
                "total_turns": len(scoped),
                "next_offset": _next_offset(
                    offset, len(page), len(scoped), explicit=explicit_ids is not None
                ),
                "turns": page,
            },
        )

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
                "each turn carries the interviewer question, the candidate answer, and tool previews. "
                "A page can come back shorter than requested (truncated): keep reading from next_offset."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "offset": {
                        "type": "integer",
                        "description": "Page offset (0-based); default 0",
                    },
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
        offset = _page_offset(args)
        limit = _page_limit(args, 10, 20)
        candidates = notes[offset : offset + limit]
        # Same rule as the ledger reader: the observation must stay valid
        # JSON, so notes that do not fit the output budget stay for the next
        # page instead of being sliced out of the serialized payload.
        return _fit_page(
            candidates,
            lambda page: {
                "offset": offset,
                "returned": len(page),
                "total": len(notes),
                "next_offset": offset + len(page) if offset + len(page) < len(notes) else None,
                "notes": page,
            },
        )

    return [
        ToolSpec(
            name="report_read_notes",
            description=(
                "Read the per-turn analysis notes produced in stage 1 (paged). "
                "A page can come back shorter than requested (truncated): keep reading from next_offset."
            ),
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
