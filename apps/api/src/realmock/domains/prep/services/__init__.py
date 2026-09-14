"""Prep services: long-term memory store, cross-session linking, and session notes shared by routes and agent tools."""

from __future__ import annotations

from realmock.domains.prep.services.memories import (
    MEMORY_BODY_MAX_CHARS,
    MEMORY_LIST_DEFAULT_LIMIT,
    MEMORY_LIST_MAX_LIMIT,
    MEMORY_SCAN_LIMIT,
    MEMORY_SUMMARY_MAX_CHARS,
    MEMORY_TAGS_MAX_COUNT,
    MEMORY_TAG_MAX_CHARS,
    clean_reasons,
    clean_tags,
    create_memory,
    find_memory_by_summary,
    get_memory,
    list_memories,
    memory_tags,
    memory_to_detail,
    memory_to_summary,
    touch_memory,
)
from realmock.domains.prep.services.linking import (
    LINKED_BLOCK_MARKER,
    REF_BLOCK_MARKER,
    format_linked_session,
    format_linked_sessions,
    strip_ref_blocks,
)
from realmock.domains.prep.services.session_notes import note_rating_into_session

__all__ = [
    "LINKED_BLOCK_MARKER",
    "REF_BLOCK_MARKER",
    "format_linked_session",
    "format_linked_sessions",
    "strip_ref_blocks",
    "MEMORY_BODY_MAX_CHARS",
    "MEMORY_LIST_DEFAULT_LIMIT",
    "MEMORY_LIST_MAX_LIMIT",
    "MEMORY_SCAN_LIMIT",
    "MEMORY_SUMMARY_MAX_CHARS",
    "MEMORY_TAGS_MAX_COUNT",
    "MEMORY_TAG_MAX_CHARS",
    "clean_reasons",
    "clean_tags",
    "create_memory",
    "find_memory_by_summary",
    "get_memory",
    "list_memories",
    "memory_tags",
    "memory_to_detail",
    "memory_to_summary",
    "note_rating_into_session",
    "touch_memory",
]
