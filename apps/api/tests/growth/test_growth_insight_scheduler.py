"""Growth insight scheduler tests (single-flight background regeneration)."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch


def _run(coro):
    return asyncio.run(coro)


def test_schedule_requires_running_loop() -> None:
    from realmock.domains.growth.services import insight_scheduler as sched

    # Sync test body: no running loop, so scheduling gives up instead of raising.
    assert sched.schedule_growth_insight_regen() is False


def test_schedule_spawns_on_running_loop() -> None:
    from realmock.domains.growth.services import insight_scheduler as sched

    async def scenario():
        async def _stub(*, locale: str = "zh-CN"):
            return None

        with patch.object(sched, "regenerate_growth_insight", _stub):
            assert sched.schedule_growth_insight_regen() is True
            # Let the spawned task run so no pending task outlives the loop.
            await asyncio.sleep(0)

    _run(scenario())


def test_regenerate_persists_and_returns_insight() -> None:
    from realmock.domains.growth.services import insight_scheduler as sched

    insight = {"headline": "v", "trajectory": "t"}
    upserted = MagicMock(id=7)

    with (
        patch.object(sched, "api_db_session", MagicMock()),
        patch.object(sched, "sessions_db_session", MagicMock()),
        patch.object(sched, "generate_growth_insight", return_value=(insight, 3)) as gen,
        patch.object(sched, "upsert_insight", return_value=upserted) as up,
    ):
        out = _run(sched.regenerate_growth_insight(locale="en"))

    assert out is insight
    assert sched.is_generating() is False
    up.assert_called_once()
    assert up.call_args.kwargs["locale"] == "en"
    assert up.call_args.kwargs["session_count"] == 3
    gen.assert_called_once()


def test_regenerate_skips_write_when_generation_fails() -> None:
    from realmock.domains.growth.services import insight_scheduler as sched

    with (
        patch.object(sched, "api_db_session", MagicMock()),
        patch.object(sched, "sessions_db_session", MagicMock()),
        patch.object(sched, "generate_growth_insight", return_value=None),
        patch.object(sched, "upsert_insight") as up,
    ):
        assert _run(sched.regenerate_growth_insight()) is None
    up.assert_not_called()
    assert sched.is_generating() is False


def test_regenerate_swallows_exceptions_and_resets_state() -> None:
    from realmock.domains.growth.services import insight_scheduler as sched

    with (
        patch.object(sched, "api_db_session", MagicMock()),
        patch.object(sched, "sessions_db_session", MagicMock()),
        patch.object(sched, "generate_growth_insight", side_effect=RuntimeError("boom")),
    ):
        assert _run(sched.regenerate_growth_insight()) is None
    assert sched.is_generating() is False


def test_regenerate_skips_while_another_run_holds_the_lock() -> None:
    from realmock.domains.growth.services import insight_scheduler as sched

    async def scenario():
        async with sched._lock:
            with patch.object(sched, "generate_growth_insight") as gen:
                assert await sched.regenerate_growth_insight() is None
                gen.assert_not_called()

    _run(scenario())
