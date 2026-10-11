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

from typing import Any

#: Assistant-row marker: this message's dialog tool_call awaits its result.
ASK_PENDING_KEY = "ask_pending"
#: Assistant-row marker: platform compaction keeps this call pair verbatim.
KEEP_TOOL_PAIR_KEY = "keep_tool_pair"

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


def _open_dialog_call_id(message: dict[str, Any]) -> str:
    """tool_call_id of the open ask_user call on a pending row ("" when absent)."""
    found = _first_open_ask_call(message, set())
    return found[1] if found else ""


def mark_paused_ask(messages: list[dict[str, Any]], event: dict[str, Any] | None) -> str:
    """Stamp the open dialog call on the loop tail (pause-time persist).

    Finds the last assistant whose ``ask_user`` call has no tool result after
    it, normalizes the call id in place (the resume path pairs by it), and
    sets the marker keys. Returns the open call id, or "" when no open call
    exists (the caller still persists the dialog payload on the display row).
    """
    if not isinstance(event, dict) or not event:
        return ""
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        if not isinstance(message.get("tool_calls"), list) or not message["tool_calls"]:
            continue
        answered = {
            str(row.get("tool_call_id") or "")
            for row in messages[index + 1 :]
            if isinstance(row, dict) and row.get("role") == "tool"
        }
        found = _first_open_ask_call(message, answered)
        if found is None:
            continue
        call, call_id, position = found
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
    call_id = _open_dialog_call_id(message)
    if not call_id:
        message.pop(ASK_PENDING_KEY, None)
        return False
    message.pop(ASK_PENDING_KEY, None)
    messages.insert(
        index + 1,
        {"role": "tool", "tool_call_id": call_id, "content": DIALOG_ANSWER_OBSERVATION},
    )
    return True


__all__ = [
    "ASK_PENDING_KEY",
    "DIALOG_ANSWER_OBSERVATION",
    "KEEP_TOOL_PAIR_KEY",
    "find_pending_ask",
    "insert_dialog_answer",
    "mark_paused_ask",
]
