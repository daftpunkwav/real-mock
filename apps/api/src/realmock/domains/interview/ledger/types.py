"""Typed shapes for the interview session ledger document."""

from __future__ import annotations

from typing import Any, NotRequired, TypedDict


class ToolPreview(TypedDict, total=False):
    """Curtain-layer tool call summary attached to an assistant turn."""

    name: str
    args_preview: Any
    result_preview: Any
    ok: bool
    chars: int


class LedgerAssistant(TypedDict, total=False):
    text: str
    visible: bool


class LedgerUser(TypedDict, total=False):
    text: str
    source: str


class LedgerTurn(TypedDict, total=False):
    """One interview turn: assistant speech, optional tools, optional user reply."""

    turn_id: str
    phase: str
    assistant: LedgerAssistant
    tools: list[ToolPreview]
    user: NotRequired[LedgerUser]
    flags: NotRequired[dict[str, Any]]


class LedgerDocument(TypedDict, total=False):
    """Root ledger document stored on ``interview_sessions.ledger``."""

    schema: str
    session_id: int
    frozen: bool
    turns: list[LedgerTurn]
    # Set when JSON parse failed; raw_unparsed preserves a truncated original blob.
    corrupt: bool
    raw_unparsed: str


__all__ = [
    "LedgerAssistant",
    "LedgerDocument",
    "LedgerTurn",
    "LedgerUser",
    "ToolPreview",
]
