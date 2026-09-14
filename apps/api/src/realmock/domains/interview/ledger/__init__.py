"""Interview session ledger: append-only dialogue + tool previews.

Public API for turn append, freeze, and pending-tool collection used by the
interview runner. Records reads frozen snapshots via platform session catalog.
"""

from __future__ import annotations

from realmock.domains.interview.ledger.constants import PREVIEW_MAX_CHARS, SCHEMA
from realmock.domains.interview.ledger.preview import truncate_preview
from realmock.domains.interview.ledger.store import (
    append_pending_tool,
    append_turn,
    begin_pending_tools,
    empty_ledger,
    freeze_ledger,
    is_frozen,
    load_ledger,
    next_turn_id,
    save_ledger,
    take_pending_tools,
)
from realmock.domains.interview.ledger.types import LedgerDocument, LedgerTurn, ToolPreview

__all__ = [
    "PREVIEW_MAX_CHARS",
    "SCHEMA",
    "LedgerDocument",
    "LedgerTurn",
    "ToolPreview",
    "append_pending_tool",
    "append_turn",
    "begin_pending_tools",
    "empty_ledger",
    "freeze_ledger",
    "is_frozen",
    "load_ledger",
    "next_turn_id",
    "save_ledger",
    "take_pending_tools",
    "truncate_preview",
]
