"""Turn-timer tests: answer-window clamp, think/answer arming, answer-timeout takeover.

Covers: clamp_answer_wait bounds/default, arm/mark/restore transitions,
_on_answer_timer_fire takeover delivery (send/set_turn/speak/mic-reopen),
_on_think_timer_fire re-arm semantics, dispatcher user_typing wiring, and the
answer_timeout prompt language split. Timers are recorded, never slept.
Conventions: SimpleNamespace ctx + AsyncMock collaborators (no network/LLM).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from realmock.domains.interview.realtime.control.turn_timers import (
    ANSWER_WAIT_MAX_SECONDS,
    ANSWER_WAIT_MIN_SECONDS,
    TurnTimersMixin,
    answer_timeout_system_prompt,
    clamp_answer_wait,
)
from realmock.domains.interview.realtime.core.events import TurnState


class _TimerHandler(TurnTimersMixin):
    """TurnTimersMixin with recorded spawns and mocked collaborators."""

    def __init__(self):
        self.ctx = SimpleNamespace(
            session_id=1,
            closing=False,
            turn_state=TurnState.USER_SPEAKING,
            last_wait_seconds=0.0,
            last_answer_wait_seconds=0.0,
            nudge_cooldown_sec=10.0,
            nudge_grace_sec=5.0,
            answer_started_at=0.0,
            answer_expired=False,
            silence_capped=False,
            think_timer_task=None,
            answer_timer_task=None,
        )
        self.spawned = []
        self.delayed = []
        self.send = AsyncMock()
        self.set_turn = AsyncMock()
        self._speak_one = AsyncMock()
        self._begin_playback_wait = MagicMock()
        self._open_mic_after_playback = AsyncMock()
        self._append_to_last_assistant = MagicMock()
        self._on_silence_nudge = AsyncMock()
        self._last_assistant_text = MagicMock(return_value="介绍一下你的项目")
        self._generate_answer_timeout_line = AsyncMock(return_value="时间差不多了，我们先继续。")

    def _spawn(self, coro):
        self.spawned.append(coro)
        task = MagicMock()
        task.done.return_value = True  # recorded spawns never "run"
        return task

    def _spawn_delayed(self, delay_s, coro):
        self.delayed.append((delay_s, coro))
        task = MagicMock()
        task.done.return_value = False
        return task


def test_clamp_answer_wait_bounds_and_default():
    assert clamp_answer_wait(0) == 120.0  # missing → default
    assert clamp_answer_wait(10) == ANSWER_WAIT_MIN_SECONDS
    assert clamp_answer_wait(999) == ANSWER_WAIT_MAX_SECONDS
    assert clamp_answer_wait(150) == 150.0


def test_answer_timeout_prompt_language_split():
    zh = answer_timeout_system_prompt()
    assert "首先" in zh and "Firstly" not in zh
    en = answer_timeout_system_prompt(lang="en")
    assert "Firstly" in en and "首先" not in en
    assert answer_timeout_system_prompt(lang="") == zh  # falsy → default


def test_turn_output_answer_wait_clamped():
    from realmock.domains.interview.agents.turn_output import parse_turn_output

    out = parse_turn_output(
        {"v": 1, "wait_seconds": 20, "answer_wait_seconds": 5000}, say_text="x"
    )
    assert out.wait_seconds == 20
    assert out.answer_wait_seconds == ANSWER_WAIT_MAX_SECONDS
    low = parse_turn_output({"answer_wait_seconds": 30}, say_text="x")
    assert low.answer_wait_seconds == ANSWER_WAIT_MIN_SECONDS
    # Missing = not provided (0); the consumer falls back to its default window.
    missing = parse_turn_output({}, say_text="x")
    assert missing.answer_wait_seconds == 0


def test_arm_resets_answer_phase_and_spawns_think_only():
    async def _scenario():
        h = _TimerHandler()
        h.ctx.last_wait_seconds = 20.0
        h.ctx.answer_started_at = 123.0
        h.ctx.answer_expired = True
        h.arm_turn_timers()
        assert h.ctx.answer_started_at == 0.0
        assert h.ctx.answer_expired is False
        # Only the think timer is armed at question time; the answer window
        # waits for the candidate's first input.
        assert len(h.delayed) == 1
        delay, _ = h.delayed[0]
        assert delay == pytest.approx(20.0)

    asyncio.run(_scenario())


def test_mark_answer_started_cancels_think_and_arms_answer_once():
    async def _scenario():
        h = _TimerHandler()
        h.ctx.last_answer_wait_seconds = 150.0
        h.arm_turn_timers()
        think_task = h.ctx.think_timer_task
        h.mark_answer_started()
        assert think_task.cancel.called is True
        assert h.ctx.think_timer_task is None
        assert h.ctx.answer_started_at > 0
        assert len(h.delayed) == 2  # think (from arm) + answer (first input)
        answer_delay = h.delayed[1][0]
        assert answer_delay == pytest.approx(150.0)
        # A second keystroke must NOT slide the deadline.
        answer_task = h.ctx.answer_timer_task
        h.mark_answer_started()
        assert h.ctx.answer_timer_task is answer_task
        assert len(h.delayed) == 2

    asyncio.run(_scenario())


def test_answer_window_ignored_when_not_user_turn():
    async def _scenario():
        h = _TimerHandler()
        h.ctx.turn_state = TurnState.AI_SPEAKING
        h.mark_answer_started()
        assert h.ctx.answer_started_at == 0.0
        assert h.delayed == []

    asyncio.run(_scenario())


def test_restore_resumes_remaining_answer_window():
    async def _scenario():
        h = _TimerHandler()
        h.ctx.last_answer_wait_seconds = 100.0
        now = asyncio.get_event_loop().time()
        h.ctx.answer_started_at = now - 40.0
        h.restore_turn_timers_after_incomplete_turn()
        assert h.delayed and h.delayed[-1][0] == pytest.approx(60.0, abs=0.01)

    asyncio.run(_scenario())


def test_restore_fires_timeout_when_window_already_over():
    async def _scenario():
        h = _TimerHandler()
        now = asyncio.get_event_loop().time()
        h.ctx.answer_started_at = now - 10_000.0
        fired = []

        def _spawn(coro):
            fired.append("spawned")
            coro.close()
            return MagicMock()

        h._spawn = _spawn  # type: ignore[method-assign]
        h.restore_turn_timers_after_incomplete_turn()
        # The overdue fire coroutine was scheduled immediately.
        assert fired == ["spawned"]

    asyncio.run(_scenario())


def test_restore_falls_back_to_think_window_without_answer():
    async def _scenario():
        h = _TimerHandler()
        h.ctx.last_wait_seconds = 30.0
        h.restore_turn_timers_after_incomplete_turn()
        assert len(h.delayed) == 1
        assert h.delayed[0][0] == pytest.approx(30.0)

    asyncio.run(_scenario())


@pytest.mark.asyncio
async def test_think_timer_fire_runs_nudge_and_rearms():
    h = _TimerHandler()
    h.ctx.last_wait_seconds = 15.0
    await h._on_think_timer_fire()
    h._on_silence_nudge.assert_awaited_once()
    # Still in think phase (nudge guards may not have delivered): re-arm keeps
    # the wake alive instead of a single lost shot.
    assert len(h.delayed) == 1


@pytest.mark.asyncio
async def test_think_timer_fire_quiet_when_answer_started():
    h = _TimerHandler()
    h.ctx.answer_started_at = asyncio.get_event_loop().time()
    await h._on_think_timer_fire()
    h._on_silence_nudge.assert_not_awaited()
    assert h.delayed == []


@pytest.mark.asyncio
async def test_answer_timeout_takes_turn_back():
    h = _TimerHandler()
    h.ctx.answer_started_at = asyncio.get_event_loop().time() - 200.0
    await h._on_answer_timer_fire()
    assert h.ctx.answer_expired is True
    h._generate_answer_timeout_line.assert_awaited_once()
    h.set_turn.assert_awaited_once_with(TurnState.PROCESSING)
    h.send.assert_awaited_once()
    assert h.send.call_args.args[0] == "silence_nudge"
    h._speak_one.assert_awaited_once_with("时间差不多了，我们先继续。")
    h._append_to_last_assistant.assert_called_once_with("时间差不多了，我们先继续。")
    h._open_mic_after_playback.assert_awaited_once()


@pytest.mark.asyncio
async def test_answer_timeout_ignored_without_answer_phase():
    h = _TimerHandler()
    await h._on_answer_timer_fire()
    assert h.ctx.answer_expired is False
    h.set_turn.assert_not_awaited()
    h._speak_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_answer_timeout_ignored_after_processing():
    h = _TimerHandler()
    h.ctx.answer_started_at = asyncio.get_event_loop().time() - 200.0
    h.ctx.turn_state = TurnState.PROCESSING
    await h._on_answer_timer_fire()
    # The candidate submitted; the interviewer replying counts as finished.
    assert h.ctx.answer_expired is False
    h._speak_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_answer_timeout_ignored_when_submit_races_generation():
    """Candidate submits while the wrap-up line is generating: never trample
    the in-flight interviewer reply (state flips during the LLM call)."""
    h = _TimerHandler()
    h.ctx.answer_started_at = asyncio.get_event_loop().time() - 200.0

    async def _submit_during_generation():
        h.ctx.turn_state = TurnState.AI_SPEAKING
        return "时间差不多了，我们先继续。"

    h._generate_answer_timeout_line = AsyncMock(side_effect=_submit_during_generation)
    await h._on_answer_timer_fire()
    h.set_turn.assert_not_awaited()
    h._speak_one.assert_not_awaited()
    h.send.assert_not_awaited()


@pytest.mark.asyncio
async def test_user_typing_dispatch_marks_answer_started():
    """Dispatcher wiring: a user_typing frame reaches mark_answer_started."""
    from realmock.domains.interview.realtime.core.message_dispatcher import (
        MessageDispatcherMixin,
    )

    marked = []

    class _H(MessageDispatcherMixin):
        ctx = SimpleNamespace(session_id=2)

        def mark_answer_started(self):
            marked.append(True)

    h = _H()
    await h._on_user_typing({})
    assert marked == [True]
