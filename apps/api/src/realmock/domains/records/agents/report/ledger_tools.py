"""Ledger reading tools for the ReAct report agents (progressive disclosure).

The frozen transcript is never dumped into the prompt in one shot: agents
pull it in bounded pages through ``ledger_overview`` / ``ledger_read_turns`` /
``ledger_search``. A batch run scopes reads to its own turn range.

Every reader returns a JSON document. The **paged** readers
(``ledger_overview`` / ``ledger_read_turns`` / ``report_read_notes``) fit
their page to the output budget by dropping trailing entries (never by
slicing the serialized text, which would cut inside a string and hand the
model an unparsable page). A trimmed page carries the continuation cursor
(and ``truncated: true`` where the payload has that field). The budget is
the agent loop's own observation cap, so a fitted page reaches the model
whole instead of being sliced there. The readers project their entries so
that one entry always fits the budget on its own.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, cast

from realmock.domains.records.agents.report.normalize import shorten_note
from realmock.platform.capabilities.ai.agent.tools.spec import ToolSpec
from realmock.platform.capabilities.ai.llm.defaults import TOOL_OBSERVATION_SOFT_CHARS
from realmock.platform.contracts.ledger_document import LedgerTurn, ToolPreview
from realmock.platform.core.coerce import coerce_int

_PAGE_TURNS = 12
_TURN_CHARS = 900
_SEARCH_HITS = 8
_SNIPPET_CHARS = 240
#: Turn ids carried per ``ledger_overview`` page. A session with a few hundred
#: turns must not push the overview observation over the agent loop's cap, so
#: the overview pages the ids like the turn reader; a window of long legacy ids
#: is trimmed further until the page fits the budget.
_OVERVIEW_IDS = 50
#: Phase labels carried in ``ledger_overview``. A phase label is plan-supplied
#: text and a plan can name any number of phases, so the list is capped in
#: count as well as in length.
_OVERVIEW_PHASES = 30
#: Serialized characters one phase label may add to the overview. The cap is
#: applied to the JSON-escaped label, not to the raw one: ``json.dumps``
#: expands a control character to a six-character ``\uXXXX`` escape, so a raw
#: character count would not bound the serialized phase list.
_PHASE_CHARS = 120
#: Characters one note may carry into a report page. A note is a teaser for
#: the report, not the evidence itself: it travels in one tool observation,
#: so a note larger than this is shortened before it reaches the page. The
#: budget leaves room for the page wrapper and stays above what the shortest
#: texts of a note add up to, so a note can always be brought under it.
_NOTE_CHARS = 9_000
#: Characters of one tool result carried into a report page. The tool output
#: is a teaser for the report, not the evidence itself: the interviewer's
#: own ledger keeps the full text.
_TOOL_PREVIEW_CHARS = 200
#: Tool previews carried per turn. A page summarizes the tool traffic of a
#: turn; the report reads the tools it needs from the next page.
_TOOLS_PER_TURN = 4
#: Serialized page budget.
#:
#: The agent loop hands a tool observation longer than
#: ``TOOL_OBSERVATION_SOFT_CHARS`` to the model sliced at that mark, which cuts
#: inside the serialized page and delivers an unparsable document. The budget
#: is therefore the loop's own cap: a fitted page must reach the model whole,
#: so a private number that can drift above that cap does not belong here.
#:
#: The page size follows from the per-turn payload (two ``_TURN_CHARS`` texts
#: plus the tool previews): a page holds as many turns as that payload fits,
#: so raising ``_PAGE_TURNS`` alone does not make a page longer.
_OUTPUT_CHARS = TOOL_OBSERVATION_SOFT_CHARS


def _turns(ledger: dict[str, Any]) -> list[LedgerTurn]:
    """Turns of a ledger document, typed against the platform contract.

    The ledger arrives as the loose dict the session snapshot carries, so the
    declared shape is asserted here. Everything downstream then reads the key
    names the contract declares.
    """
    turns = ledger.get("turns")
    if not isinstance(turns, list):
        return []
    return [cast("LedgerTurn", t) for t in turns if isinstance(t, dict)]


def _turn_text(turn: LedgerTurn) -> str:
    parts: list[str] = []
    for val in (turn.get("assistant"), turn.get("user")):
        if isinstance(val, dict):
            parts.append(str(val.get("text", "")))
        elif val:
            parts.append(str(val))
    return " ".join(parts).lower()


def _project_tool_preview(tool: ToolPreview) -> dict[str, Any]:
    """Project one tool preview for a report page.

    The keys are read as subscripts, so a key the platform contract does not
    declare is a type error here instead of a preview that silently loses the
    tool output. A preview that lacks a key still projects.
    """
    try:
        name: str | None = tool["name"]
    except KeyError:
        name = None
    try:
        result = tool["result_preview"]
    except KeyError:
        result = ""
    return {"name": name, "preview": str(result)[:_TOOL_PREVIEW_CHARS]}


def _project_turn(turn: LedgerTurn) -> dict[str, Any]:
    """Project one turn for a report page.

    The tool preview keys come from the platform contract, so the page
    carries the tool result the interviewer-side call returned.
    """
    assistant = turn.get("assistant")
    user = turn.get("user")
    tools = turn.get("tools") or []
    return {
        "turn_id": turn.get("turn_id"),
        "phase": turn.get("phase"),
        "question": str(assistant.get("text", ""))[:_TURN_CHARS]
        if isinstance(assistant, dict)
        else "",
        "answer": str(user.get("text", ""))[:_TURN_CHARS] if isinstance(user, dict) else "",
        "tools": [_project_tool_preview(t) for t in tools[:_TOOLS_PER_TURN] if isinstance(t, dict)],
    }


def _next_offset(offset: int, returned: int, total: int) -> int | None:
    """Offset cursor for the next page (None at the end of the transcript).

    The cursor points at the first entry that did not fit, so a trimmed page
    never skips the entries the model has not seen yet. The count of the
    delivered entries is the only length that matters: a page that was trimmed
    delivered fewer entries than the window holds, and a cursor built from the
    window would step over the rest of the page.
    """
    consumed = offset + returned
    return consumed if consumed < total else None


def _clip_json_text(text: str, max_escaped: int) -> str:
    """Longest prefix of ``text`` whose JSON-escaped form fits ``max_escaped``.

    ``json.dumps`` expands control characters to six-character escapes, so a
    raw character count does not bound the serialized length of a plan-supplied
    phase label or of a turn id preserved from a legacy payload. The escaped
    length of a prefix grows with the prefix, so the longest fitting prefix is
    found by bisection. When even the empty prefix exceeds the budget, the
    empty string is returned.
    """
    if len(json.dumps(text, ensure_ascii=False)) - 2 <= max_escaped:
        return text
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if len(json.dumps(text[:middle], ensure_ascii=False)) - 2 <= max_escaped:
            low = middle
        else:
            high = middle - 1
    return text[:low]


def _fit_page(entries: list[Any], payload_for: Callable[[list[Any]], dict[str, Any]]) -> str:
    """Serialize one page of entries as JSON that fits the output budget.

    The observation must stay parsable: slicing the serialized text cuts
    inside a string and hands the model an unparsable page. Trailing entries
    are dropped instead, and the page is marked ``truncated`` so the model
    knows to keep reading. One entry is always kept, so the paging cursor
    advances even when a single entry alone exceeds the budget; the readers
    project their entries so that one entry always fits it.
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


def _fit_overview(offset: int, phases: list[str], ids: list[str]) -> str:
    """Serialize one overview page as JSON that fits the output budget.

    ``json.dumps`` expands control characters, so the page is measured after
    serialization: the phase labels are already clipped to their escaped
    budgets, and the id window is trimmed here until the document fits.
    Trailing ids are dropped first, never sliced out of the serialized text,
    and the continuation cursor follows the delivered window. The page always
    fits once the window is down to one id (the phase list is capped and the
    offset is clamped); an id preserved from a legacy payload can be longer
    than the whole budget by itself, and that last id is clipped to the room
    the wrapper leaves - an id that long is not a usable cursor anyway.
    """
    window = ids[offset : offset + _OVERVIEW_IDS]
    while True:
        payload = {
            "offset": offset,
            "total_turns": len(ids),
            "phases": phases,
            "turn_ids": window,
            "next_offset": _next_offset(offset, len(window), len(ids)),
        }
        raw = json.dumps(payload, ensure_ascii=False)
        if len(raw) <= _OUTPUT_CHARS:
            return raw
        if len(window) > 1:
            window.pop()
            continue
        wrapper = json.dumps({**payload, "turn_ids": [""]}, ensure_ascii=False)
        window[0] = _clip_json_text(window[0], _OUTPUT_CHARS - len(wrapper))


def _page_offset(args: dict[str, Any], default: int = 0) -> int:
    """Page offset from model-supplied args; a non-numeric value degrades to the start.

    Malformed paging arguments are a model mistake, not a broken tool: the
    other readers (resume raw text, memory index, web search) degrade to their
    default instead of raising, so one bad argument must not fail the call and
    cost the agent a round. A non-finite value (Infinity) counts as malformed
    too, so it degrades to the default like any other unusable value.
    """
    return max(0, coerce_int(args.get("offset") or default, default))


def _page_limit(args: dict[str, Any], default: int, maximum: int) -> int:
    """Page size from model-supplied args; a non-numeric value degrades to the default."""
    return max(1, min(coerce_int(args.get("limit") or default, default), maximum))


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

    async def overview(args: dict[str, Any]) -> str:
        # The phase labels are plan-supplied text and a legacy payload can
        # preserve an arbitrarily long turn id, so neither list is bounded by
        # the ledger. Labels are de-duplicated on their full value first (two
        # phases that share a prefix are still two phases) and then clipped to
        # a JSON-escaped length; the id page is fitted to the remaining budget
        # by _fit_overview, so the observation cannot reach the loop's slicer
        # (the failure the page fitter exists to prevent).
        phases: list[str] = []
        seen_phases: set[str] = set()
        for turn in scoped:
            phase = str(turn.get("phase") or "")
            if not phase or phase in seen_phases:
                continue
            seen_phases.add(phase)
            phases.append(_clip_json_text(phase, _PHASE_CHARS))
            if len(phases) >= _OVERVIEW_PHASES:
                break
        ids = [str(t.get("turn_id")) for t in scoped]
        # A model-supplied offset is any integer; clamping it to the end of the
        # ledger keeps the echoed cursor, and therefore the page, bounded.
        offset = min(_page_offset(args), len(ids))
        return _fit_overview(offset, phases, ids)

    async def read_turns(args: dict[str, Any]) -> str:
        offset = _page_offset(args)
        requested = args.get("turn_ids")
        explicit_ids = requested if isinstance(requested, list) and requested else None
        if explicit_ids is not None:
            want = {str(t) for t in explicit_ids[: _PAGE_TURNS * 2]}
            candidates = [t for t in scoped if str(t.get("turn_id")) in want]
            # The offset counts within the requested turns, so a page that was
            # trimmed can be continued at the first turn that did not fit.
            total = len(candidates)
            candidates = candidates[offset:]
        else:
            candidates = scoped[offset : offset + _PAGE_TURNS]
            total = len(scoped)
        projected = [_project_turn(t) for t in candidates]
        return _fit_page(
            projected,
            lambda page: {
                "offset": offset,
                "returned": len(page),
                "total_turns": total,
                "next_offset": _next_offset(offset, len(page), total),
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
            description=(
                "Overview of the frozen interview transcript: turn count, phase list, "
                "ordered turn ids (paged — pass offset for the next page of ids)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "offset": {
                        "type": "integer",
                        "description": "Turn-id page offset (0-based); default 0",
                    },
                },
                "required": [],
            },
            handler=overview,
        ),
        ToolSpec(
            name="ledger_read_turns",
            description=(
                "Read transcript turns by page (offset-based) or by explicit turn_ids; "
                "each turn carries the interviewer question, the candidate answer, and tool previews. "
                "A page can come back shorter than requested (truncated): keep reading from next_offset "
                "(pass the same turn_ids again when you asked for specific ones)."
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
        # Same rule as the ledger reader: the observation must stay valid
        # JSON, so notes that do not fit the output budget stay for the next
        # page instead of being sliced out of the serialized payload. A note
        # that does not fit on its own is shortened, so one note can never
        # exceed the budget by itself.
        candidates = [shorten_note(note, _NOTE_CHARS) for note in notes[offset : offset + limit]]
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
