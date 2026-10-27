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
whole instead of being sliced there.

Every page projects its entries to that budget. Free text is clipped by its
JSON-escaped length rather than its character count (``json.dumps`` expands
a control character to a six-character escape), and a turn id or phase label
that does not fit becomes a bounded handle: the clipped value plus a digest
of the full one, so handles stay distinct and map back to the ledger text.
The ledger tools match ids through the same projection, so an id advertised
by ``ledger_overview`` or ``ledger_search`` still resolves its turn, and a
single projected entry always fits the budget on its own.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any, cast

from realmock.domains.records.agents.report.normalize import shorten_note
from realmock.platform.capabilities.ai.agent.tools.spec import ToolSpec
from realmock.platform.capabilities.ai.llm.defaults import TOOL_OBSERVATION_SOFT_CHARS
from realmock.platform.contracts.ledger_document import LedgerTurn, ToolPreview
from realmock.platform.core.coerce import coerce_int

_PAGE_TURNS = 12
#: Serialized characters of one question/answer carried into a turn page.
_TURN_CHARS = 900
_SEARCH_HITS = 8
#: Serialized characters of one keyword-search snippet.
_SNIPPET_CHARS = 240
#: Turn ids carried per ``ledger_overview`` page. The overview pages a long
#: session's ids like the turn reader, so one observation stays bounded.
_OVERVIEW_IDS = 50
#: Phase labels carried in ``ledger_overview``. The cap only truncates a
#: ledger that carries more distinct phases than this; the page reports that
#: through ``total_phases`` / ``phases_truncated``.
_OVERVIEW_PHASES = 30
#: Serialized characters one turn id may add to a page. A live ledger writes
#: short ``t-0001`` ids; a legacy payload can preserve a longer one, so ids
#: are projected to a bounded handle that still resolves the turn (see
#: :func:`_bounded_handle`).
_TURN_ID_CHARS = 120
#: Serialized characters one phase label may add to the overview. A phase
#: label is plan-supplied text; a label preserved from a legacy payload is
#: bounded like a turn id, and the digest keeps clipped labels distinct.
_PHASE_CHARS = 120
#: Serialized characters of one phase label carried into a turn page. A turn
#: page is where a phase label abbreviated by the overview is read in full:
#: the bound is high enough that only a label far beyond a plan title is
#: clipped, and it still leaves room for the two texts and the tool previews
#: of one turn inside the observation budget.
_TURN_PHASE_CHARS = 6_000
#: Characters one note may carry into a report page. A note is a teaser for
#: the report, not the evidence itself: it travels in one tool observation,
#: so a note larger than this is shortened before it reaches the page. The
#: budget leaves room for the page wrapper and stays above what the shortest
#: texts of a note add up to, so a note can always be brought under it.
_NOTE_CHARS = 9_000
#: Serialized characters of one tool result carried into a report page. The
#: tool output is a teaser for the report, not the evidence itself: the
#: interviewer's own ledger keeps the full text.
_TOOL_PREVIEW_CHARS = 200
#: Serialized characters of one tool name carried by a preview.
_TOOL_NAME_CHARS = 80
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


def _json_escaped_chars(text: str) -> int:
    """Serialized length of ``text`` as a JSON string, surrounding quotes excluded."""
    return len(json.dumps(text, ensure_ascii=False)) - 2


def _clip_json_text(text: str, max_escaped: int) -> str:
    """Longest prefix of ``text`` whose JSON-escaped form fits ``max_escaped``.

    ``json.dumps`` expands control characters to six-character escapes, so a
    raw character count does not bound the serialized length of a plan-supplied
    phase label or of a turn id preserved from a legacy payload. The escaped
    length of a prefix grows with the prefix, so the longest fitting prefix is
    found by bisection. When even the empty prefix exceeds the budget, the
    empty string is returned.
    """
    if _json_escaped_chars(text) <= max_escaped:
        return text
    low, high = 0, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if _json_escaped_chars(text[:middle]) <= max_escaped:
            low = middle
        else:
            high = middle - 1
    return text[:low]


def _digest(text: str) -> str:
    """Eight hexadecimal digits identifying one full text behind a handle.

    Not a security primitive: the digest only keeps long values that share a
    clipped prefix distinguishable after projection.
    """
    return hashlib.blake2s(text.encode("utf-8", "surrogatepass"), digest_size=4).hexdigest()


def _bounded_handle(text: str, max_escaped: int) -> str:
    """Bounded handle for a turn id or phase label.

    A live ledger writes short turn ids and plan titles, but a legacy payload
    can preserve any string, and an over-long value cannot travel in one tool
    observation. The handle keeps the value's prefix and appends a digest of
    the full value, so it fits ``max_escaped`` serialized characters, values
    that share a prefix stay distinct, and the ledger tools can map the handle
    back to the ledger text. Projecting a handle again returns it unchanged, so
    advertised ids and raw ledger ids match through the same projection.
    """
    if _json_escaped_chars(text) <= max_escaped:
        return text
    digest = _digest(text)
    head = _clip_json_text(text, max_escaped - len(digest) - 1)
    return f"{head}…{digest}"


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
    return {
        "name": None if name is None else _clip_json_text(str(name), _TOOL_NAME_CHARS),
        "preview": _clip_json_text(str(result), _TOOL_PREVIEW_CHARS),
    }


def _project_turn(turn: LedgerTurn) -> dict[str, Any]:
    """Project one turn for a report page.

    Every text is bounded by its serialized length, which is what the page
    budget is spent on, so one projected turn always fits the budget on its
    own. The identity fields use :func:`_bounded_handle`, so a legacy id or
    phase label stays bounded and its handle still maps back to the ledger.
    The tool preview keys come from the platform contract, so the page carries
    the tool result the interviewer-side call returned.
    """
    assistant = turn.get("assistant")
    user = turn.get("user")
    tools = turn.get("tools") or []
    return {
        "turn_id": _bounded_handle(str(turn.get("turn_id")), _TURN_ID_CHARS),
        "phase": _bounded_handle(str(turn.get("phase") or ""), _TURN_PHASE_CHARS),
        "question": _clip_json_text(str(assistant.get("text", "")), _TURN_CHARS)
        if isinstance(assistant, dict)
        else "",
        "answer": _clip_json_text(str(user.get("text", "")), _TURN_CHARS)
        if isinstance(user, dict)
        else "",
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


def _fit_page(entries: list[Any], payload_for: Callable[[list[Any]], dict[str, Any]]) -> str:
    """Serialize one page of entries as JSON that fits the output budget.

    The observation must stay parsable: slicing the serialized text cuts
    inside a string and hands the model an unparsable page. Trailing entries
    are dropped instead, and the page is marked ``truncated`` so the model
    knows to keep reading. One entry is always kept, so the paging cursor
    advances even when a single entry alone exceeds the budget; the readers
    project every entry so that one entry always fits it.
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
        # Every field is bounded by construction: phase labels and turn ids
        # are projected to handles that fit the budget, the phase list is
        # capped and reports its own truncation, and the ids are a page, so a
        # session with hundreds of turns or a legacy payload cannot push this
        # observation into the loop's slicer.
        phases: list[str] = []
        seen_phases: set[str] = set()
        phases_truncated = False
        for turn in scoped:
            phase = str(turn.get("phase") or "")
            if not phase or phase in seen_phases:
                continue
            seen_phases.add(phase)
            label = _bounded_handle(phase, _PHASE_CHARS)
            phases_truncated = phases_truncated or label != phase
            if len(phases) < _OVERVIEW_PHASES:
                phases.append(label)
        if len(seen_phases) > len(phases):
            phases_truncated = True
        ids = [_bounded_handle(str(t.get("turn_id")), _TURN_ID_CHARS) for t in scoped]
        # A model-supplied offset is any integer; clamping it to the end of the
        # ledger keeps the echoed cursor small.
        offset = min(_page_offset(args), len(ids))
        window = ids[offset : offset + _OVERVIEW_IDS]
        return json.dumps(
            {
                "offset": offset,
                "total_turns": len(ids),
                "phases": phases,
                "total_phases": len(seen_phases),
                "phases_truncated": phases_truncated,
                "turn_ids": window,
                "next_offset": _next_offset(offset, len(window), len(ids)),
            },
            ensure_ascii=False,
        )

    async def read_turns(args: dict[str, Any]) -> str:
        offset = _page_offset(args)
        requested = args.get("turn_ids")
        explicit_ids = requested if isinstance(requested, list) and requested else None
        if explicit_ids is not None:
            # Match on the advertised projection, so the handle an overview or
            # search returned resolves the turn it names. A raw id still
            # matches: a short id projects to itself, and a legacy long id
            # projects to the same handle the tools advertise.
            want = {
                _bounded_handle(str(t), _TURN_ID_CHARS) for t in explicit_ids[: _PAGE_TURNS * 2]
            }
            candidates = [
                t for t in scoped if _bounded_handle(str(t.get("turn_id")), _TURN_ID_CHARS) in want
            ]
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
        hits: list[dict[str, Any]] = []
        for turn in scoped:
            text = _turn_text(turn)
            if keyword in text:
                idx = text.find(keyword)
                snippet = text[max(0, idx - 40) : idx + _SNIPPET_CHARS]
                hits.append(
                    {
                        "turn_id": _bounded_handle(str(turn.get("turn_id")), _TURN_ID_CHARS),
                        "snippet": _clip_json_text(snippet, _SNIPPET_CHARS),
                    }
                )
            if len(hits) >= _SEARCH_HITS:
                break
        return json.dumps({"matches": hits}, ensure_ascii=False)

    return [
        ToolSpec(
            name="ledger_overview",
            description=(
                "Overview of the frozen interview transcript: turn count, phase list, "
                "ordered turn ids (paged — pass offset for the next page of ids). "
                "Phase labels may be shortened and total_phases/phases_truncated say "
                "whether the list is complete; ledger_read_turns carries each turn's phase "
                "label, which is only shortened when it exceeds the page budget itself."
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
                "each turn carries the interviewer question, the candidate answer, the phase label, "
                "and tool previews. Turn ids may come from the overview or the search tool. "
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
