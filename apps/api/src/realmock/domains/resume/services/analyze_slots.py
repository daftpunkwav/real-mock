"""In-process concurrency cap for resume deep review.

Responsibilities:
- Non-blocking slot acquire/release for long LLM analyses
- Fail immediately with A1007 when this process is at capacity

Slots are per-process (not shared across workers). Must not import ORM
or interpret review payloads.
"""

from __future__ import annotations

import asyncio

from realmock.platform.core.errors import raise_error
from realmock.domains.resume.schemas.limits import MAX_PARALLEL_ANALYZE

_active_analyses = 0
_slot_lock = asyncio.Lock()


async def acquire_slot() -> None:
    """Non-blocking slot: if full, raise A1007 immediately (never queue)."""
    global _active_analyses
    async with _slot_lock:
        if _active_analyses >= MAX_PARALLEL_ANALYZE:
            raise_error("A1007")
        _active_analyses += 1


async def release_slot() -> None:
    """Release one in-flight analysis slot (never below zero)."""
    global _active_analyses
    async with _slot_lock:
        if _active_analyses > 0:
            _active_analyses -= 1


def reset_slots_for_tests() -> None:
    """Drop the in-process counter. Tests only."""
    global _active_analyses
    _active_analyses = 0
