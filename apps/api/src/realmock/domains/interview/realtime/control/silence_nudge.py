"""Silence follow-up orchestration (WS mixin): trigger conditions + follow-up delivery + history integration.

Timing anchor: the interviewer's speech END (``ctx.speech_end_at``), never the
text-complete moment — long TTS playback must not eat the candidate's
thinking time. The per-question wait comes from the turn LLM
(``ctx.last_wait_seconds``, clamped 7-60s); the static cooldown is only a
backstop. After two probes for one question, a single closing nudge is spoken
("can't hear you, type instead") and the question goes quiet — no probe loops,
no error spam.

LLM generation of realistic follow-ups is in :mod:`silence_probe` (this module does not duplicate the generation logic).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from realmock.platform.database import SessionLocal
from realmock.domains.interview.realtime.core.events import TurnState

if TYPE_CHECKING:
    from realmock.domains.interview.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)

#: LLM-provided wait bounds (seconds): the interviewer personality/strictness/
#: style and question difficulty decide within this window; out-of-range values
#: snap to the nearest bound.
NUDGE_WAIT_MIN_SECONDS = 7.0
NUDGE_WAIT_MAX_SECONDS = 60.0

#: Max LLM probes for one question before the closing nudge takes over.
NUDGE_PROBE_CAP = 2

_CLOSING_NUDGE = {
    "zh": "我这边一直听不到你的声音，可能是麦克风没收到。你可以直接在下方打字回答，我们继续。",
    "en": "I still can't hear you — your mic may not be picking up. Feel free to type your answer below and we'll carry on.",
}


def clamp_nudge_wait(value: float, default: float) -> float:
    """Resolve the effective nudge wait: LLM estimate wins, clamped to 7-60s.

    Args:
        value: latest turn ``wait_seconds`` (<= 0 means not provided).
        default: static backstop cooldown (room config).
    """
    candidate = float(value) if value and value > 0 else float(default or 0)
    if candidate <= 0:
        candidate = NUDGE_WAIT_MIN_SECONDS
    return min(NUDGE_WAIT_MAX_SECONDS, max(NUDGE_WAIT_MIN_SECONDS, candidate))


class SilenceNudgeMixin:
    """Silence follow-up orchestration; depends on ctx fields + _generate_silence_probe (SilenceProbeMixin)."""

    ctx: "ConnectionContext"

    def _nudge_language(self) -> str:
        """Closing-nudge language from the flow plan ("en" or "zh")."""
        agent = self.ctx.agent
        plan = getattr(agent, "plan", None) if agent is not None else None
        if plan is not None and getattr(plan, "source", "") == "agent":
            lang = str(getattr(plan, "language", "zh") or "zh")
            return "en" if lang.strip().lower().startswith("en") else "zh"
        return "zh"

    async def _on_silence_nudge(self) -> None:
        """Realistic silence follow-up: use the reasoning LLM to generate one in real time from the current
question/follow-up plan/silence count.

        Follow up at most twice for the same question (first encourage the candidate to speak,
        then provide a direct hint); then speak ONE closing nudge and go quiet for that
        question. Appends follow-up text to the previous assistant utterance to preserve
        alternating message roles (required by the Anthropic protocol).
        """
        if self.ctx.turn_state != TurnState.USER_SPEAKING:
            return
        # Guard: interviewer audio still in flight (client hasn't reported
        # playback done) — never nudge over our own voice.
        if self.ctx.tts_sent_this_turn and not self.ctx.playback_done.is_set():
            return
        now = asyncio.get_event_loop().time()
        anchor = self.ctx.speech_end_at or self.ctx.mic_opened_at
        if anchor and now - anchor < self.ctx.nudge_grace_sec:
            return
        cooldown = clamp_nudge_wait(
            self.ctx.last_wait_seconds, self.ctx.nudge_cooldown_sec
        )
        if now - self.ctx.last_nudge_at < cooldown:
            return
        # New question resets the probe budget (memory-only, no DB needed).
        question = self._last_assistant_text()
        if question != self.ctx.silence_probe_question:
            self.ctx.silence_probe_question = question
            self.ctx.silence_probe_seq = 0
            self.ctx.silence_capped = False
        if self.ctx.silence_capped:
            self.ctx.last_nudge_at = now
            return
        self.ctx.last_nudge_at = now
        if self.ctx.silence_probe_seq >= NUDGE_PROBE_CAP:
            await self._speak_closing_nudge()
            self.ctx.silence_capped = True
            return
        self.ctx.silence_probe_seq += 1

        db = SessionLocal()
        try:
            session = self._load_session(db)
            if not session:
                return
            state = getattr(self.ctx.agent, "agent_state", {}) or {}
            probe_hint = str(state.get("last_probe") or "")
            silent_sec = int(now - anchor) if anchor else 0

            probe_text = await self._generate_silence_probe(
                question=question,
                probe_hint=probe_hint,
                attempt=self.ctx.silence_probe_seq,
                silent_sec=silent_sec,
            )
            if not probe_text or probe_text == self.ctx.last_silence_probe:
                probe_text = self.ctx.orchestrator.build_silence_nudge(
                    session.personality,
                    session.strictness,
                    phase=session.current_phase,
                )
            self.ctx.last_silence_probe = probe_text

            await self.set_turn(TurnState.PROCESSING)
            await self.send(
                "silence_nudge",
                content=probe_text,
                seq=self.ctx.silence_probe_seq,
            )
            self._begin_playback_wait()
            await self._speak_one(probe_text)
            self._append_to_last_assistant(probe_text)
            # Short single-sentence prompt while the candidate is silent: wait the
            # playback out before reopening the mic.
            await self._open_mic_after_playback(wait_playback=True)
        finally:
            try:
                db.close()
            except Exception:
                logger.debug(
                    "silence_nudge DB close failed sid=%s",
                    self.ctx.session_id,
                    exc_info=True,
                )

    async def _speak_closing_nudge(self) -> None:
        """Last resort for a silent question: say "can't hear you, type instead" once.

        Same delivery as a probe (spoken + appended to history) so the turn
        stays well-formed; the question is then capped and stays quiet.
        """
        text = _CLOSING_NUDGE[self._nudge_language()]
        self.ctx.last_silence_probe = text
        await self.set_turn(TurnState.PROCESSING)
        await self.send(
            "silence_nudge",
            content=text,
            seq=NUDGE_PROBE_CAP + 1,
        )
        self._begin_playback_wait()
        await self._speak_one(text)
        self._append_to_last_assistant(text)
        await self._open_mic_after_playback(wait_playback=True)

    def _last_assistant_text(self) -> str:
        """The most recent interviewer's statement in the message history (the contextual anchor for realistic questioning)."""
        if not self.ctx.agent:
            return ""
        for m in reversed(self.ctx.agent.messages):
            if m.get("role") == "assistant":
                return str(m.get("content") or "")
        return ""

    def _append_to_last_assistant(self, text: str) -> None:
        """Merge the follow-up question into the latest assistant statement to avoid consecutive assistants in the message history."""
        if not self.ctx.agent or not text:
            return
        for m in reversed(self.ctx.agent.messages):
            if m.get("role") == "assistant":
                content = str(m.get("content") or "")
                m["content"] = f"{content}\n{text}" if content else text
                return


__all__ = ["NUDGE_PROBE_CAP", "NUDGE_WAIT_MAX_SECONDS", "NUDGE_WAIT_MIN_SECONDS", "SilenceNudgeMixin", "clamp_nudge_wait"]
