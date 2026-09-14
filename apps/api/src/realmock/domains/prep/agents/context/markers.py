"""Shared markers and bucket keys for prep context blocks.

Single source for prompt-cache-stable prefixes: every strip/upsert helper
matches on these prefixes, so a rename must update all of them together.
Session-linking markers live in services/linking.py (shared with routes);
re-exported here so ``agents.context`` imports keep working.
"""

from __future__ import annotations

from realmock.domains.prep.services.linking import LINKED_BLOCK_MARKER, REF_BLOCK_MARKER

# Reply-language hint marker: upsert_lang_hint strips older copies by prefix.
LANG_HINT_MARKER = "[Reply language]"
# Per-turn context-usage hint marker (see upsert_usage_hint).
USAGE_HINT_MARKER = "[Context usage]"

# Context-breakdown bucket keys (stable API contract for GET .../context).
BREAKDOWN_USER = "user"
BREAKDOWN_ASSISTANT = "assistant"
BREAKDOWN_THINKING = "thinking"
BREAKDOWN_TOOLS = "tools"
BREAKDOWN_SYSTEM = "system"
BREAKDOWN_MEMORY = "memory"
BREAKDOWN_OTHER = "other"
BREAKDOWN_ORDER = (
    BREAKDOWN_USER,
    BREAKDOWN_ASSISTANT,
    BREAKDOWN_THINKING,
    BREAKDOWN_TOOLS,
    BREAKDOWN_SYSTEM,
    BREAKDOWN_MEMORY,
    BREAKDOWN_OTHER,
)


__all__ = [
    "BREAKDOWN_ASSISTANT",
    "BREAKDOWN_MEMORY",
    "BREAKDOWN_ORDER",
    "BREAKDOWN_OTHER",
    "BREAKDOWN_SYSTEM",
    "BREAKDOWN_THINKING",
    "BREAKDOWN_TOOLS",
    "BREAKDOWN_USER",
    "LANG_HINT_MARKER",
    "LINKED_BLOCK_MARKER",
    "REF_BLOCK_MARKER",
    "USAGE_HINT_MARKER",
]
