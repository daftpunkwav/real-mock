"""Prep context assembly: system prompt blocks, resume/profile/company context, memory inject.

The orchestrator (agent) mainly calls build_system_messages (first-turn seed)
and build_working_context (per-turn assembly); it also reads PREP_SYSTEM and
normalize_ui_locale directly, while chat routes use format_linked_sessions
and strip_ref_blocks. Leaf modules: seed / linked / hints / working / markers.
"""

from __future__ import annotations

from realmock.domains.prep.agents.context.hints import (
    build_lang_hint,
    build_usage_hint,
    infer_text_locale,
    normalize_ui_locale,
    upsert_lang_hint,
    upsert_usage_hint,
)
from realmock.domains.prep.agents.context.linked import (
    format_linked_session,
    format_linked_sessions,
    strip_ref_blocks,
)
from realmock.domains.prep.agents.context.markers import (
    BREAKDOWN_ASSISTANT,
    BREAKDOWN_MEMORY,
    BREAKDOWN_ORDER,
    BREAKDOWN_OTHER,
    BREAKDOWN_SYSTEM,
    BREAKDOWN_THINKING,
    BREAKDOWN_TOOLS,
    BREAKDOWN_USER,
    LANG_HINT_MARKER,
    LINKED_BLOCK_MARKER,
    REF_BLOCK_MARKER,
    USAGE_HINT_MARKER,
)
from realmock.domains.prep.agents.context.seed import (
    PREP_SYSTEM,
    build_system_message,
    build_system_messages,
    format_memory_index,
)
from realmock.domains.prep.agents.context.working import build_context_breakdown, build_working_context

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
    "PREP_SYSTEM",
    "REF_BLOCK_MARKER",
    "USAGE_HINT_MARKER",
    "build_context_breakdown",
    "build_lang_hint",
    "build_system_message",
    "build_system_messages",
    "build_usage_hint",
    "build_working_context",
    "format_linked_session",
    "format_linked_sessions",
    "format_memory_index",
    "infer_text_locale",
    "normalize_ui_locale",
    "strip_ref_blocks",
    "upsert_lang_hint",
    "upsert_usage_hint",
]
