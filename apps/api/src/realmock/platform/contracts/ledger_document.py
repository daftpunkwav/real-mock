"""Cross-domain shape of the interview session ledger document.

Responsibilities:
- Declare the key names of the ledger document, its turns, and the tool
  previews attached to a turn. The interview domain is the sole writer; other
  domains read the document through the session catalog port, whose
  ``get_ledger`` hands it over typed as ``LedgerDocument``.

Contracts:
- The key names below are the single source of truth. A reader that is typed
  against these shapes cannot look up a key the writer never produces: the
  mismatch is a type error instead of a silently empty value.

Constraints:
- Shapes only. No business logic and no domain imports: the writer (interview)
  and every reader (records) depend on this package, never on each other.
"""

from __future__ import annotations

from typing import Any, TypedDict


class ToolPreview(TypedDict, total=False):
    """Tool call summary attached to an assistant turn.

    The args and the result are truncated previews, not the full tool
    output: the ledger keeps what a reader needs to see that a tool ran.
    Readers key their lookups on these declared names; the ledger store
    normalizes a stored preview written under an older key to the declared
    one before publishing the document.
    """

    name: str
    args_preview: Any
    result_preview: Any
    ok: bool
    chars: int


class LedgerAssistant(TypedDict, total=False):
    """Assistant speech of one turn."""

    text: str
    visible: bool


class LedgerUser(TypedDict, total=False):
    """Candidate reply of one turn."""

    text: str
    source: str


class LedgerTurn(TypedDict, total=False):
    """One interview turn: assistant speech, optional tools, optional user reply."""

    turn_id: str
    phase: str
    assistant: LedgerAssistant
    tools: list[ToolPreview]
    user: LedgerUser
    flags: dict[str, Any]


class LedgerDocument(TypedDict, total=False):
    """Root ledger document aggregated from the ``interview_turns`` table.

    Every element of ``turns`` is a turn mapping with tool previews under the
    declared key names: the writer skips a row that is not a mapping and
    normalizes the previews of a row it publishes. A skipped row or a dropped
    preview marks the document ``corrupt``, so a reader can tell an absent
    turn from one the document could not represent.
    """

    schema: str
    session_id: int
    frozen: bool
    turns: list[LedgerTurn]
    # Set when stored content cannot be represented in this document
    # (unparsable JSON, a non-mapping turn, a dropped tool preview);
    # raw_unparsed preserves a truncated original blob.
    corrupt: bool
    raw_unparsed: str


__all__ = [
    "LedgerAssistant",
    "LedgerDocument",
    "LedgerTurn",
    "LedgerUser",
    "ToolPreview",
]
