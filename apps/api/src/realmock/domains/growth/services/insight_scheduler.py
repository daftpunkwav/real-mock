"""Background regeneration of the growth insight (single-flight)."""

from __future__ import annotations

import asyncio
import logging

from realmock.domains.growth.agents.insight import generate_growth_insight
from realmock.domains.growth.services.insight_store import upsert_insight
from realmock.platform.database import api_db_session, sessions_db_session

logger = logging.getLogger(__name__)

# Module-level single-flight state: interview finishes land on the one uvicorn
# event loop, so a plain lock + flag is enough (no cross-process claims needed
# for this local, single-user deployment).
_lock = asyncio.Lock()
_state: dict[str, bool] = {"generating": False}
# Hold task references so the fire-and-forget regen cannot be garbage-collected
# mid-flight (same pattern as resume's schedule_resume_parse).
_tasks: set[asyncio.Task] = set()


def is_generating() -> bool:
    """True while a regeneration task is in flight (for GET status)."""
    return bool(_state["generating"])


async def regenerate_growth_insight(*, locale: str = "zh-CN") -> dict | None:
    """Run one insight generation and persist it. Never raises."""
    if _lock.locked():
        logger.info("growth insight regen skipped: already running")
        return None
    async with _lock:
        _state["generating"] = True
        try:
            with api_db_session() as api_db, sessions_db_session() as sessions_db:
                result = await generate_growth_insight(api_db, sessions_db, locale=locale)
                if result is not None:
                    insight, session_count = result
                    row = upsert_insight(
                        sessions_db,
                        insight,
                        locale=locale,
                        session_count=session_count,
                    )
                    logger.info("growth insight regenerated id=%s", row.id)
                    return insight
                return None
        except Exception:
            logger.exception("growth insight regeneration failed")
            return None
        finally:
            _state["generating"] = False


def schedule_growth_insight_regen(*, locale: str = "zh-CN") -> bool:
    """Fire-and-forget background regen from the ingest hook.

    Returns True when a task was scheduled. Safe to call from a sync context
    with a running loop (the report-summary hook always runs inside one);
    without a loop it logs and gives up — the next finished interview or a
    manual refresh will regenerate anyway.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("growth insight regen skipped: no running event loop")
        return False
    task = loop.create_task(regenerate_growth_insight(locale=locale))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return True


__all__ = ["is_generating", "regenerate_growth_insight", "schedule_growth_insight_regen"]
