"""Typed shapes for the interview session ledger document.

The shapes live in :mod:`realmock.platform.contracts.ledger_document` because
the ledger is read across domains: interview writes it, records reads it
through the session catalog seam. One declaration keeps the writer's key names
and every reader's key lookups in sync.
"""

from __future__ import annotations

from realmock.platform.contracts.ledger_document import (
    LedgerAssistant,
    LedgerDocument,
    LedgerTurn,
    LedgerUser,
    ToolPreview,
)

__all__ = [
    "LedgerAssistant",
    "LedgerDocument",
    "LedgerTurn",
    "LedgerUser",
    "ToolPreview",
]
