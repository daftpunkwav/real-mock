"""Shared context for a WebSocket interview session.

Consolidates host fields scattered across TYPE_CHECKING declarations in the InterviewWSHandler mixins
into an explicit dataclass, eliminating implicit coupling.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from realmock.domains.interview.realtime.nudge.orchestrator import InterviewOrchestrator
from realmock.domains.interview.realtime.core.events import TurnState
from realmock.domains.interview.agents import InterviewRunner, InterviewSessionState
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.capabilities.voice.stt import SttCredentials
from realmock.platform.capabilities.voice.tts import TtsCredentials
from realmock.platform.capabilities.voice.tts.voice_resolve import VoiceProsody


@dataclass
class ConnectionContext:
    """All mutable state for a WebSocket interview session.

    Constructed by InterviewWSHandler.__init__ and passed to each mixin.
    Mixin methods read and write through self.ctx.xxx and no longer depend on TYPE_CHECKING declarations.
    """

    # ──Connect ────────────────────────────────────
    ws: WebSocket
    session_id: int
    client_access_token: str = ""
    ws_subprotocol: str | None = None
    superseded: bool = False
    lease_token: str = field(default_factory=lambda: uuid.uuid4().hex)

    # ──Talk turn status ────────────────────────────────
    turn_state: TurnState = TurnState.IDLE

    # ──Business object (assigned in handle)──────────────────
    orchestrator: InterviewOrchestrator = field(default_factory=InterviewOrchestrator)
    agent: InterviewSessionState | None = None
    llm: LLMClient | None = None
    runner: InterviewRunner | None = None

    # ── Audio buffering ───────────────────────────────
    audio_buffer: list[str] = field(default_factory=list)
    audio_buffer_bytes: int = 0

    # ── TTS ───────────────────────────────────────
    tts_voice: str = ""
    session_prosody: VoiceProsody = field(default_factory=lambda: VoiceProsody(voice=""))
    tts_creds: TtsCredentials = field(default_factory=lambda: TtsCredentials(handler="edge"))
    tts_soft_idx: int = 0

    # ── STT ───────────────────────────────────────
    stt_creds: SttCredentials = field(default_factory=lambda: SttCredentials(provider="local", model="base"))
    whisper_model: str = ""
    stt_fail_streak: int = 0

    # ── Word Wheel Lock ───────────────────────────────────
    turn_busy: bool = False
    busy_epoch: int = 0
    stream_epoch: int = 0
    closing: bool = False

    # ── Play ─────────────────────────────────────
    playback_done: asyncio.Event = field(default_factory=asyncio.Event)
    playback_generation: int = 0
    awaiting_playback_gen: int = 0
    playback_wait_timeout_sec: float = 45.0
    tts_sent_this_turn: bool = False
    #: Loop-clock stamp of the last tts_audio send; lets the silence-nudge
    #: guard detect a lost client tts_playback_done instead of staying
    #: silent forever.
    last_tts_sent_at: float = 0.0

    # ── Interruption ────────────────────────────────────
    candidate_interrupts: int = 0
    ai_interrupts: int = 0
    mic_opened_at: float = 0.0

    # ── Questioning silently ────────────────────────────────
    last_nudge_at: float = 0.0
    nudge_cooldown_sec: float = 10.0
    nudge_grace_sec: float = 5.0
    #: Anchored when the interviewer's speech actually ends (client
    #: tts_playback_done, or mic-open with no audio pending) — silence timing
    #: counts from here, NOT from text-complete (mic_opened_at), so long TTS
    #: playback never eats the candidate's thinking time.
    speech_end_at: float = 0.0
    #: Latest LLM per-question wait estimate (seconds, 0 = not provided).
    last_wait_seconds: float = 0.0
    #: Last C2001 error frame sent (STT-failure errors back off to avoid spam).
    last_stt_error_at: float = 0.0
    silence_probe_seq: int = 0          # Silence probes sent for current question (0=none yet; max 2).
    #: Assistant message count when the current probe window started. A new
    #: question is a new assistant message, so this is the exact window key —
    #: probes/closing text are appended to the same message and never reset it.
    silence_probe_msg_count: int = 0
    silence_probe_question: str = ""    # Question text of the current probe window (set when a new one opens)
    last_silence_probe: str = ""        # Content of the previous probe (to avoid repeating it)
    #: Closing nudge already spoken for the current question (after the probe
    #: cap): further silence stays quiet instead of looping probes or errors.
    silence_capped: bool = False

    # ── Server-side turn timers (think window / answer window) ──────
    #: Latest LLM per-question answer-window estimate (seconds, 0 = not provided).
    last_answer_wait_seconds: float = 0.0
    #: Scheduled think-window timer for the current question (None = disarmed);
    #: fires the silence-nudge pipeline when the candidate has not started.
    think_timer_task: asyncio.Task[Any] | None = None
    #: Scheduled answer-window timer (None = not started); armed at the
    #: candidate's FIRST input with a fixed deadline from that moment.
    answer_timer_task: asyncio.Task[Any] | None = None
    #: Loop-clock stamp of the candidate's first input (typing uplink or STT
    #: partial); 0 = still in the think phase.
    answer_started_at: float = 0.0
    #: The interviewer already took the turn back for this question (answer
    #: window expiry); no further nudges/timeouts until the next question.
    answer_expired: bool = False

    # ── Tips/Reports ─────────────────────────────
    hint_inflight: str | None = None
    #: Reference-answer depth snapshot from the session row ("outline" | "full").
    reference_detail: str = "outline"
    report_task: asyncio.Task[Any] | None = None

    # ── Background tasks ────────────────────────────────
    bg_tasks: set[asyncio.Task[Any]] = field(default_factory=set)

    # ──TTS queue (injected by ws_handler)─────────────
    tts_queue: Any = None  # _SentenceTTSQueue, avoid circular import
