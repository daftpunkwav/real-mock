"""Linked-session context (thin re-export over services/linking).

Single truth lives in services/linking.py so routes and agents share it
without routes importing the agent layer. Kept for backward-compatible
``agents.context`` imports; new code imports from services directly.
"""

from __future__ import annotations

from realmock.domains.prep.services.linking import (
    LINKED_BLOCK_MARKER,
    format_linked_session,
    format_linked_sessions,
    strip_ref_blocks,
)

__all__ = [
    "LINKED_BLOCK_MARKER",
    "format_linked_session",
    "format_linked_sessions",
    "strip_ref_blocks",
]
