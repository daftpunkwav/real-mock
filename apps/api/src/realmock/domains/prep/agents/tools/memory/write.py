"""Memory write tool: durable long-term memory with idempotency."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from realmock.domains.prep.agents.tools.spec import SearchHits, ToolSpec
from realmock.domains.prep.schemas import MEMORY_ORIGINS
from realmock.domains.prep.services import create_memory, find_memory_by_summary
from realmock.platform.capabilities.ai.agent import WorkingMemory
from realmock.platform.database import sessions_db_session

# Serializes long-term memory inserts from the same process: tool rounds run
# siblings concurrently, and parallel SQLite commits raise "database is locked".
# Best-effort single-process coalescing; cross-process workers rely on SQLite busyTimeout.
_MEMORY_WRITE_LOCK = asyncio.Lock()

# Idempotency-key marker remembered in working memory: "memory-key:<key>=#<id>".
_MEMORY_KEY_NOTE_PREFIX = "memory-key:"
_IDEMPOTENCY_KEY_MAX_CHARS = 64


def _normalize_idempotency_key(raw: Any) -> str:
    """Normalize the caller-supplied dedupe key; empty means no dedupe."""
    return str(raw or "").strip()[:_IDEMPOTENCY_KEY_MAX_CHARS]


def _find_key_note_id(memory: WorkingMemory, key: str) -> int | None:
    """Find a previously recorded idempotency-key marker in working memory."""
    prefix = f"{_MEMORY_KEY_NOTE_PREFIX}{key}=#"
    for note in memory.notes:
        idx = str(note).find(prefix)
        if idx < 0:
            continue
        try:
            return int(str(note)[idx + len(prefix):].split()[0])
        except (TypeError, ValueError, IndexError):
            continue
    return None


def _write_memory_sync(
    summary: str, user_input: str, agent_output: str, tags: list[str], origin: str
) -> tuple[int, bool]:
    """Insert one memory row (exact-summary dedupe); runs inside ``asyncio.to_thread``.

    Storage lookup lives in services; this helper only owns the session scope.

    Returns ``(memory_id, deduplicated)``.
    """
    with sessions_db_session() as db:
        existing = find_memory_by_summary(db, summary)
        if existing is not None:
            return int(existing.id), True
        row = create_memory(
            db,
            summary=summary,
            user_input=user_input,
            agent_output=agent_output,
            tags=tags,
            origin=origin,
        )
        return int(row.id), False


async def run_memory_write(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
    """Durable memory write with turn-level + row-level idempotency.

    Retried turns must not duplicate rows: an explicit ``idempotency_key`` is
    remembered in working memory (same-turn retries hit it), and an exact
    summary match in the store short-circuits re-inserts (cross-turn retries).
    A process-wide lock serializes concurrent inserts from the same tool round
    (SQLite ``database is locked`` under parallel commits).

    Args:
        args: Tool arguments (``summary`` required one-line index;
            ``user_input``/``agent_output`` source turns; ``tags`` list;
            ``origin`` user_rating/user_emphasis/agent_note;
            ``idempotency_key`` optional dedupe key).
        memory: Working memory receiving the index note and key marker.

    Returns:
        ``(json_text, [])`` with the memory ``id`` (plus ``deduplicated``
        when an existing row was reused).
    """
    summary = str(args.get("summary") or "").strip()
    if not summary:
        return "memory_write missing summary; nothing recorded.", []
    origin = str(args.get("origin") or "agent_note")
    if origin not in MEMORY_ORIGINS:
        origin = "agent_note"
    tags = args.get("tags") if isinstance(args.get("tags"), list) else []
    key = _normalize_idempotency_key(args.get("idempotency_key"))
    async with _MEMORY_WRITE_LOCK:
        if key:
            hit = _find_key_note_id(memory, key)
            if hit is not None:
                return json.dumps(
                    {"id": hit, "summary": summary[:200], "deduplicated": True},
                    ensure_ascii=False,
                ), []
        memory_id, deduplicated = await asyncio.to_thread(
            _write_memory_sync,
            summary,
            str(args.get("user_input") or ""),
            str(args.get("agent_output") or ""),
            [str(t) for t in tags],
            origin,
        )
        memory.remember("note", f"Long-term memory #{memory_id}: {summary[:160]}")
        if key:
            memory.remember("note", f"{_MEMORY_KEY_NOTE_PREFIX}{key}=#{memory_id}")
    payload: dict[str, Any] = {"id": memory_id, "summary": summary[:200]}
    if deduplicated:
        payload["deduplicated"] = True
    return json.dumps(payload, ensure_ascii=False), []


MEMORY_WRITE_SPEC = ToolSpec(
    name="memory_write",
    description=(
        "Record a durable long-term memory (user facts, preferences, rated feedback). "
        "Summary must be one line (≤200 chars), topic-organized; only record what "
        "future turns cannot infer. Never record turn trivia. "
        "Before writing, use search_tools to find the memory query tools and "
        "check for duplicate topics. At most 2 writes per turn; batch distinct "
        "facts into fewer calls."
    ),
    parameters={
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "One-line index (required)"},
            "user_input": {"type": "string"},
            "agent_output": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "origin": {
                "type": "string",
                "enum": ["user_rating", "user_emphasis", "agent_note"],
            },
            "idempotency_key": {
                "type": "string",
                "description": (
                    "Optional dedupe key for retried turns (e.g. a stable topic id). "
                    "Repeating a key returns the existing memory instead of inserting a duplicate."
                ),
            },
        },
        "required": ["summary"],
    },
    handler=run_memory_write,
)


__all__ = ["MEMORY_WRITE_SPEC", "run_memory_write"]
