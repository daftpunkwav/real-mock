"""Guard: the ledger document shape stays shared between writer and readers.

The interview domain writes the session ledger; the records domain reads it
through the session catalog seam, whose payload is an untyped dict. Both sides
take their key names from ``platform/contracts/ledger_document.py``, so a key
the writer produces and a key a reader looks up cannot drift apart.

These tests hold that contract:

- the writer produces exactly the tool preview keys the contract declares;
- the interview domain re-exports the contract shapes instead of copying them.
"""

from __future__ import annotations

from realmock.domains.interview.ledger.store import build_tool_preview
from realmock.platform.contracts.ledger_document import (
    LedgerAssistant,
    LedgerDocument,
    LedgerTurn,
    LedgerUser,
    ToolPreview,
)


def test_the_writer_produces_the_declared_tool_preview_keys() -> None:
    """The writer must produce exactly the keys the contract declares."""
    written = build_tool_preview("web_search", {"q": "kafka"}, "result text")
    assert set(written) == set(ToolPreview.__annotations__)


def test_the_interview_ledger_types_are_the_platform_contract() -> None:
    """The interview domain must re-export the contract shapes, not copy them.

    A second declaration in the domain would let the writer and the readers
    drift apart again, which is the defect this contract exists to prevent.
    """
    from realmock.domains.interview.ledger import types as interview_types

    assert interview_types.ToolPreview is ToolPreview
    assert interview_types.LedgerAssistant is LedgerAssistant
    assert interview_types.LedgerUser is LedgerUser
    assert interview_types.LedgerTurn is LedgerTurn
    assert interview_types.LedgerDocument is LedgerDocument
