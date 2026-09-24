"""Per-session turn mutual exclusion.

Two concurrent turns on one session (double click, two tabs) each load the
same history and save last-writer-wins, silently dropping the earlier turn.
A process-wide keyed lock serializes them; entries are refcounted so a queued
waiter keeps its entry alive and the map never grows for the process lifetime.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

# session id -> (lock, holders + queued waiters)
_LOCKS: dict[int, tuple[asyncio.Lock, int]] = {}


@asynccontextmanager
async def session_turn_lock(session_id: int) -> AsyncIterator[None]:
    """Hold one session's turn lock for the enclosed block."""
    entry = _LOCKS.get(session_id)
    if entry is None:
        entry = (asyncio.Lock(), 0)
        _LOCKS[session_id] = entry
    lock, refs = entry
    _LOCKS[session_id] = (lock, refs + 1)
    try:
        await lock.acquire()
        try:
            yield
        finally:
            lock.release()
    finally:
        _, refs = _LOCKS[session_id]
        if refs <= 1:
            # Last interested party: drop the entry (the lock is released or
            # about to be; a fresh turn builds a new one).
            _LOCKS.pop(session_id, None)
        else:
            _LOCKS[session_id] = (lock, refs - 1)


__all__ = ["session_turn_lock"]
