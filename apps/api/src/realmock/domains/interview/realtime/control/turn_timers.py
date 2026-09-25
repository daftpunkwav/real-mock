"""Server-owned turn timers (WS mixin): think window + answer window.

The nudge used to fire only when the client reported ``silence_timeout``, so any
client-side disarm (e.g. repeated STT failures) silently postponed follow-ups
forever. The server now owns the clocks, armed when a question turn completes
(``arm_turn_timers`` from the streaming consumer):

- think window (``ctx.last_wait_seconds``, clamped 7-60s): when it expires
  without any candidate input, the existing silence-nudge pipeline runs; the
  timer re-arms itself so the nudge guards eventually pass instead of the
  wake being lost once.
- answer window (``ctx.last_answer_wait_seconds``, clamped 90-300s): armed at
  the candidate's FIRST input (``user_typing`` uplink or ``stt_text`` partial)
  with a fixed deadline from that moment; when it expires without a finished
  answer, the interviewer politely takes the turn back
  (``_on_answer_timer_fire``).

Client ``silence_timeout`` stays supported as an early wake for the think
window, never as the only trigger.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from realmock.domains.interview.agents import strip_think_blocks
from realmock.domains.interview.realtime.control.prompts import answer_timeout_system_prompt
from realmock.domains.interview.realtime.control.silence_nudge import clamp_nudge_wait
from realmock.domains.interview.realtime.control.silence_probe import flow_language
from realmock.domains.interview.realtime.core.events import TurnState

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from realmock.domains.interview.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)

#: Answer-window bounds (seconds); out-of-range/missing LLM values snap in.
ANSWER_WAIT_MIN_SECONDS = 90.0
ANSWER_WAIT_MAX_SECONDS = 300.0
ANSWER_WAIT_DEFAULT_SECONDS = 120.0

_ANSWER_TIMEOUT_FALLBACK = {
    "zh": "时间差不多了，这一题先到这里，我们往下走。",
    "en": "We're about out of time on this one — let's wrap it here and move on.",
}


def clamp_answer_wait(value: float) -> float:
    """Resolve the effective answer window: LLM estimate wins, clamped to 90-300s."""
    candidate = float(value) if value and value > 0 else ANSWER_WAIT_DEFAULT_SECONDS
    return min(ANSWER_WAIT_MAX_SECONDS, max(ANSWER_WAIT_MIN_SECONDS, candidate))


class TurnTimersMixin:
    """Think/answer timers; depends on ctx fields + _spawn/send/set_turn and the
    silence-nudge pipeline (``_on_silence_nudge``)."""

    ctx: "ConnectionContext"

    if TYPE_CHECKING:
        # Members provided by sibling mixins of the composed InterviewWSHandler.
        _spawn: Callable[..., "asyncio.Task[Any]"]
        _on_silence_nudge: Callable[..., Coroutine[Any, Any, None]]
        set_turn: Callable[[TurnState], Coroutine[Any, Any, None]]
        send: Callable[..., Coroutine[Any, Any, None]]
        _begin_playback_wait: Callable[..., None]
        _speak_one: Callable[..., Coroutine[Any, Any, None]]
        _open_mic_after_playback: Callable[..., Coroutine[Any, Any, None]]
        _append_to_last_assistant: Callable[..., None]
        _last_assistant_text: Callable[..., str]

    # ── arming ────────────────────────────────────────────────
    def arm_turn_timers(self) -> None:
        """(Re)arm the think window for a freshly asked question; resets the answer phase."""
        self.cancel_turn_timers()
        self.ctx.answer_started_at = 0.0
        self.ctx.answer_expired = False
        self.arm_think_timer()

    def arm_think_timer(self) -> None:
        """Arm/re-arm only the think window (periodic retry until guards pass)."""
        think_s = clamp_nudge_wait(
            self.ctx.last_wait_seconds, self.ctx.nudge_cooldown_sec
        )
        self.ctx.think_timer_task = self._spawn_delayed(
            think_s, self._on_think_timer_fire
        )

    def cancel_turn_timers(self) -> None:
        """Cancel both timers (new question, candidate turn started, teardown)."""
        for attr in ("think_timer_task", "answer_timer_task"):
            task: asyncio.Task[Any] | None = getattr(self.ctx, attr)
            if task is not None and not task.done():
                task.cancel()
            setattr(self.ctx, attr, None)

    def mark_answer_started(self) -> None:
        """First candidate input (typing or STT partial) moves think → answer phase.

        The answer deadline is fixed at this moment (no sliding reset), so an
        unfinished answer always hands the turn back eventually.
        """
        if self.ctx.closing or self.ctx.answer_expired:
            return
        if self.ctx.turn_state != TurnState.USER_SPEAKING:
            return
        now = asyncio.get_event_loop().time()
        if self.ctx.answer_started_at == 0.0:
            self.ctx.answer_started_at = now
        think_task = self.ctx.think_timer_task
        if think_task is not None and not think_task.done():
            think_task.cancel()
        self.ctx.think_timer_task = None
        answer_task = self.ctx.answer_timer_task
        if answer_task is None or answer_task.done():
            answer_s = clamp_answer_wait(self.ctx.last_answer_wait_seconds)
            self.ctx.answer_timer_task = self._spawn_delayed(
                answer_s, self._on_answer_timer_fire
            )

    def restore_turn_timers_after_incomplete_turn(self) -> None:
        """A candidate turn ended WITHOUT a completed answer (e.g. empty STT
        transcript): resume whichever window is still relevant."""
        if self.ctx.closing or self.ctx.answer_expired:
            return
        if self.ctx.answer_started_at:
            remaining = (
                self.ctx.answer_started_at
                + clamp_answer_wait(self.ctx.last_answer_wait_seconds)
                - asyncio.get_event_loop().time()
            )
            if remaining <= 0:
                self._spawn(self._on_answer_timer_fire())
            elif self.ctx.answer_timer_task is None or self.ctx.answer_timer_task.done():
                self.ctx.answer_timer_task = self._spawn_delayed(
                    remaining, self._on_answer_timer_fire
                )
            return
        self.arm_think_timer()

    def _spawn_delayed(self, delay_s: float, fire: Any) -> asyncio.Task[Any]:
        """Spawn ``fire()`` after ``delay_s``; ``fire`` is a zero-arg coroutine factory.

        The coroutine is created only when the timer actually fires, so a timer
        cancelled mid-sleep never leaks an un-awaited coroutine (RuntimeWarning).
        """

        async def _runner() -> None:
            await asyncio.sleep(max(0.0, delay_s))
            await fire()

        return self._spawn(_runner())

    # ── firing ────────────────────────────────────────────────
    async def _on_think_timer_fire(self) -> None:
        """Think window expired: run the nudge pipeline, then keep retrying
        periodically until the guards pass or the phase changes."""
        if self.ctx.closing or self.ctx.answer_started_at:
            return
        try:
            await self._on_silence_nudge()
        except Exception:
            logger.exception(
                "think timer nudge failed sid=%s", self.ctx.session_id
            )
        still_thinking = (
            not self.ctx.answer_started_at
            and not self.ctx.silence_capped
            and not self.ctx.closing
            and not self.ctx.answer_expired
        )
        if still_thinking:
            self.arm_think_timer()

    async def _on_answer_timer_fire(self) -> None:
        """Answer window expired without a finished answer: the interviewer
        politely takes the turn back (same lightweight delivery as the closing
        nudge)."""
        if self.ctx.closing or self.ctx.answer_expired:
            return
        if not self.ctx.answer_started_at:
            return
        if self.ctx.turn_state != TurnState.USER_SPEAKING:
            # The candidate just submitted and the interviewer is replying —
            # the answer counted as finished.
            return
        self.ctx.answer_expired = True
        text = await self._generate_answer_timeout_line()
        # Re-check after the LLM call: the candidate may have submitted or
        # requested finish while the wrap-up line was generating; taking the
        # turn now would trample the in-flight interviewer reply/closing.
        if self.ctx.closing or self.ctx.turn_state != TurnState.USER_SPEAKING:
            return
        await self.set_turn(TurnState.PROCESSING)
        await self.send("silence_nudge", content=text, seq=4)
        self._begin_playback_wait()
        await self._speak_one(text)
        self._append_to_last_assistant(text)
        await self._open_mic_after_playback(wait_playback=True)

    async def _generate_answer_timeout_line(self) -> str:
        """LLM wrap-up line for answer expiry; template on failure."""
        fallback = _ANSWER_TIMEOUT_FALLBACK[flow_language(getattr(self.ctx, "agent", None))]
        if self.ctx.llm is None:
            return fallback
        question = self._last_assistant_text()[:300]
        system = answer_timeout_system_prompt(lang=flow_language(getattr(self.ctx, "agent", None)))
        user = f"Current question: {question or '(none)'}"
        try:
            raw = await self.ctx.llm.chat(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.7,
                max_tokens=120,
            )
        except Exception:
            logger.warning(
                "answer time-up line generation failed sid=%s; using template",
                self.ctx.session_id,
                exc_info=True,
            )
            return fallback
        raw = strip_think_blocks(raw or "").strip()
        try:
            parsed = json.loads(raw)
        except Exception:
            return raw[:120] or fallback
        if isinstance(parsed, dict):
            say = str(parsed.get("say") or "").strip()
            return say[:120] or fallback
        return raw[:120] or fallback


__all__ = [
    "ANSWER_WAIT_DEFAULT_SECONDS",
    "ANSWER_WAIT_MAX_SECONDS",
    "ANSWER_WAIT_MIN_SECONDS",
    "TurnTimersMixin",
    "answer_timeout_system_prompt",
    "clamp_answer_wait",
]
