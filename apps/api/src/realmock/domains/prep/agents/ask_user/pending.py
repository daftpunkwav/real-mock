"""Paused-dialog state: the ask_user tool_call stays open until the user answers.

Contract (see :mod:`dispatch`): a valid dialog raises :class:`AgentPause`, the
loop keeps the assistant ``tool_calls`` message WITHOUT a tool result, and the
turn segment ends. The next user input — popup answer or free-typed text — is
that dialog's answer: the resume path inserts a pointer tool result (facts
only; the answer itself stays in the user message) directly after the open
call and re-enters the loop on the SAME turn, so the interrupted task remains
the live task instead of the reply reading like a new topic.

Marker keys (persisted on history rows; display consumers ignore them):
- ``ask_pending`` on the assistant row: its dialog call awaits the answer.
- ``keep_tool_pair`` on the assistant row: platform rule-based compaction
  must keep this declaration and its tool rows verbatim (the rows are tiny,
  and collapsing them would orphan the open call or erase the exchange).

The ``ask`` dialog payload keeps riding the display (waiting-line) row exactly
as before, so history rendering is unchanged.
"""

from __future__ import annotations

import json
from typing import Any

#: Assistant-row marker: this message's dialog tool_call awaits its result.
ASK_PENDING_KEY = "ask_pending"
#: Assistant-row marker: platform compaction keeps this call pair verbatim.
KEEP_TOOL_PAIR_KEY = "keep_tool_pair"
#: Assistant-row marker: the ORIGINAL task text frozen at pause time, so a
#: later resume of a SEQUENTIAL dialog still gates text-gated tools from the
#: task even after earlier dialog exchanges (pointer included) have folded.
RESUME_TASK_KEY = "resume_task_text"

#: Pointer observation completing the open call at resume time. Facts only —
#: the answer itself is the following user message (one copy, in the
#: strongest attention position; no duplication in the tool result).
DIALOG_ANSWER_OBSERVATION = (
    "[ask_user] The user answered the dialog; their reply follows as the next message."
)


def find_pending_ask(messages: list[dict[str, Any]] | None) -> int | None:
    """Index of the assistant row whose dialog call still awaits its answer.

    Only one dialog can be open at a time; the scan runs from the end and
    tolerates corrupt shapes. Returns None when nothing is pending.
    """
    for index in range(len(messages or []) - 1, -1, -1):
        message = messages[index]  # type: ignore[index]
        if isinstance(message, dict) and message.get(ASK_PENDING_KEY):
            if message.get("role") == "assistant":
                return index
            return None
    return None


def _first_open_ask_call(
    message: dict[str, Any], answered: set[str]
) -> tuple[dict[str, Any], str, int] | None:
    """First ask_user call on the row without a stored result.

    Returns ``(call, call_id, position)``, or None when every ask_user call
    already carries a tool result (or the row declares none).
    """
    calls = message.get("tool_calls")
    if not isinstance(calls, list):
        return None
    for position, call in enumerate(calls):
        if not isinstance(call, dict):
            continue
        function = call.get("function") or {}
        if str(function.get("name") or "") != "ask_user":
            continue
        call_id = str(call.get("id") or "")
        if call_id and call_id in answered:
            continue
        return call, call_id, position
    return None


def _open_ask_calls(
    message: dict[str, Any], answered: set[str]
) -> list[tuple[dict[str, Any], str, int]]:
    """Every ask_user call on the row without a stored result, in order."""
    calls = message.get("tool_calls")
    if not isinstance(calls, list):
        return []
    found: list[tuple[dict[str, Any], str, int]] = []
    for position, call in enumerate(calls):
        if not isinstance(call, dict):
            continue
        function = call.get("function") or {}
        if str(function.get("name") or "") != "ask_user":
            continue
        call_id = str(call.get("id") or "")
        if call_id and call_id in answered:
            continue
        found.append((call, call_id, position))
    return found


def original_task_text(messages: list[dict[str, Any]], pending_index: int) -> str:
    """Content of the user row that owns the live task behind a pending dialog.

    Scans backwards from the pending row and skips dialog answers (a user row
    directly following its pointer result), so a SECOND dialog pause in the
    same task freezes the toolset from the original task text instead of the
    previous answer (whose text carries none of the task's gating signals).
    Returns "" when history has no plain task row.
    """
    for index in range(pending_index - 1, -1, -1):
        message = messages[index]
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        pointer = messages[index - 1] if index else None
        owner = messages[index - 2] if index > 1 else None
        if (
            isinstance(pointer, dict)
            and pointer.get("role") == "tool"
            and pointer.get("content") == DIALOG_ANSWER_OBSERVATION
            and isinstance(owner, dict)
            and owner.get("role") == "assistant"
        ):
            continue  # an answered dialog's reply, not the task
        return str(message.get("content") or "")
    return ""


def _answered_call_ids(messages: list[dict[str, Any]], from_index: int) -> set[str]:
    """tool_call_ids of results stored after ``messages[from_index]``.

    Shared pairing scan for the pause-time marker and the resume-time pointer:
    an ask_user call whose id is in this set already carries its result and
    must never be picked as the open dialog.
    """
    return {
        str(row.get("tool_call_id") or "")
        for row in messages[from_index + 1 :]
        if isinstance(row, dict) and row.get("role") == "tool"
    }


def _open_dialog_call_id(message: dict[str, Any], answered: set[str]) -> str:
    """tool_call_id of the open ask_user call on a pending row ("" when absent).

    ``answered`` must carry the ids of the results following the pending row:
    resolving against an empty set would pair an earlier, already-answered
    dialog call and leave the real open call dangling.
    """
    found = _first_open_ask_call(message, answered)
    return found[1] if found else ""


def _arguments_question(call: dict[str, Any]) -> str:
    """The question text inside a dialog call's arguments ("" when unreadable)."""
    try:
        payload = json.loads(str((call.get("function") or {}).get("arguments") or "{}"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return ""
    question = payload.get("question") if isinstance(payload, dict) else None
    return str(question) if isinstance(question, str) else ""


def mark_paused_ask(messages: list[dict[str, Any]], event: dict[str, Any] | None) -> str:
    """Stamp the open dialog call on the loop tail (pause-time persist).

    Finds the last assistant whose ``ask_user`` call has no tool result after
    it, normalizes the call id in place (the resume path pairs by it), and
    sets the marker keys. When a round carries several unanswered dialog
    calls (a cancelled round can leave the invalid one's result unlanded),
    the call whose arguments carry the EVENT's question wins — the displayed
    dialog is the one awaiting the answer. Returns the open call id, or ""
    when no open call exists (the caller still persists the dialog payload
    on the display row).
    """
    if not isinstance(event, dict) or not event:
        return ""
    asked_question = str(event.get("question") or "")
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        if not isinstance(message.get("tool_calls"), list) or not message["tool_calls"]:
            continue
        answered = _answered_call_ids(messages, index)
        found = _first_open_ask_call(message, answered)
        if found is None:
            continue
        call, call_id, position = found
        if asked_question:
            # Prefer the call that actually emitted this dialog over an
            # earlier unanswered (e.g. invalid-args) sibling.
            for other_call, other_id, other_position in _open_ask_calls(message, answered):
                if _arguments_question(other_call) == asked_question:
                    call, call_id, position = other_call, other_id, other_position
                    break
        if not call_id:
            call_id = f"call_{index}_ask_user_{position}"
            call["id"] = call_id
        message[ASK_PENDING_KEY] = True
        message[KEEP_TOOL_PAIR_KEY] = True
        return call_id
    return ""


def insert_dialog_answer(messages: list[dict[str, Any]], index: int) -> bool:
    """Complete the open dialog call with the pointer observation (resume time).

    Inserts the tool result directly after the pending assistant message and
    clears ``ask_pending`` (the exchange is closed; ``keep_tool_pair`` stays so
    the tiny pair survives rule-based compaction). Returns False when the row
    carries no resolvable call id — the stale marker is dropped so the input
    runs as a normal turn instead.
    """
    if not 0 <= index < len(messages):
        return False
    message = messages[index]
    call_id = _open_dialog_call_id(message, _answered_call_ids(messages, index))
    if not call_id:
        message.pop(ASK_PENDING_KEY, None)
        return False
    message.pop(ASK_PENDING_KEY, None)
    messages.insert(
        index + 1,
        {"role": "tool", "tool_call_id": call_id, "content": DIALOG_ANSWER_OBSERVATION},
    )
    return True


def undo_dialog_answer(messages: list[dict[str, Any]], index: int) -> None:
    """Restore the pre-resume pending state after a failed turn preparation.

    Inverse of :func:`insert_dialog_answer`: removes the pointer result and
    re-stamps ``ask_pending``, so a failed prepare persists history that still
    resumes on the next input instead of silently converting the answer into a
    new task (see ``chat._prepare_turn``). Best-effort: a missing pointer row
    (never inserted, or already folded) still gets its marker back.
    """
    if not 0 <= index < len(messages):
        return
    message = messages[index]
    pointer = messages[index + 1] if index + 1 < len(messages) else None
    if (
        isinstance(pointer, dict)
        and pointer.get("role") == "tool"
        and pointer.get("content") == DIALOG_ANSWER_OBSERVATION
    ):
        messages.pop(index + 1)
    message[ASK_PENDING_KEY] = True


def stamp_resume_task(messages: list[dict[str, Any]], task_text: str | None) -> None:
    """Record the frozen task text on the pending row (pause-time persist).

    Read back by the next resume: after earlier dialog exchanges fold away,
    text-based answer detection can no longer reach the original task, so the
    pause row itself carries the authoritative value. When the caller has no
    explicit value (the FIRST pause of a task — its resume text was never
    computed), the user row behind the pending declaration is used: folding
    may later remove it, but the stamp has already captured it. Display
    consumers and the LLM client ignore unknown row keys.
    """
    for index, message in enumerate(messages):
        if not (isinstance(message, dict) and message.get(ASK_PENDING_KEY)):
            continue
        value = task_text if isinstance(task_text, str) and task_text else None
        if value is None:
            value = original_task_text(messages, index)
        if value:
            message[RESUME_TASK_KEY] = value
        return


__all__ = [
    "ASK_PENDING_KEY",
    "DIALOG_ANSWER_OBSERVATION",
    "KEEP_TOOL_PAIR_KEY",
    "RESUME_TASK_KEY",
    "find_pending_ask",
    "insert_dialog_answer",
    "mark_paused_ask",
    "original_task_text",
    "stamp_resume_task",
    "undo_dialog_answer",
]
