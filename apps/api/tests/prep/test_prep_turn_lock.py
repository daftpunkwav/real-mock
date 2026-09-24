"""Per-session turn lock (services/turn_lock.py)."""

from __future__ import annotations

import asyncio

import pytest

from realmock.domains.prep.services import session_turn_lock
from realmock.domains.prep.services.turn_lock import _LOCKS


@pytest.fixture(autouse=True)
def _clean_locks():
    _LOCKS.clear()
    yield
    _LOCKS.clear()


async def test_lock_serializes_same_session() -> None:
    """Two holders on one session run strictly one after the other."""
    active = 0
    max_active = 0

    async def turn() -> None:
        nonlocal active, max_active
        async with session_turn_lock(1):
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            active -= 1

    await asyncio.gather(turn(), turn(), turn())
    assert max_active == 1


async def test_lock_is_per_session() -> None:
    """Different sessions never block each other."""
    active = 0
    max_active = 0

    async def turn(sid: int) -> None:
        nonlocal active, max_active
        async with session_turn_lock(sid):
            active += 1
            max_active = max(max_active, active)
            await asyncio.sleep(0.01)
            active -= 1

    await asyncio.gather(turn(1), turn(2), turn(3))
    assert max_active == 3


async def test_lock_map_is_refcounted_and_cleaned() -> None:
    """Entries disappear with their last interested party, even when a waiter
    queued behind a holder (the waiter's own ref keeps the entry alive)."""
    release_first = asyncio.Event()
    order: list[str] = []

    async def holder() -> None:
        async with session_turn_lock(7):
            order.append("holder-in")
            await release_first.wait()
        order.append("holder-out")

    async def waiter() -> None:
        async with session_turn_lock(7):
            order.append("waiter-in")
        order.append("waiter-out")

    holder_task = asyncio.create_task(holder())
    await asyncio.sleep(0.01)
    waiter_task = asyncio.create_task(waiter())
    await asyncio.sleep(0.01)
    # Both parties registered; the entry must exist while a waiter queues.
    assert 7 in _LOCKS
    release_first.set()
    await asyncio.gather(holder_task, waiter_task)
    assert order[:2] == ["holder-in", "holder-out"]
    assert order[2:] == ["waiter-in", "waiter-out"]
    # Nobody left interested: the map is empty again.
    assert 7 not in _LOCKS
