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
from realmock.domains.interview.agents.session_state import InterviewSessionState
from realmock.domains.interview.agents.runner import InterviewRunner
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

    # ── Interruption ────────────────────────────────────
    candidate_interrupts: int = 0
    ai_interrupts: int = 0
    mic_opened_at: float = 0.0

    # ── Questioning silently ────────────────────────────────
    last_nudge_at: float = 0.0
    nudge_cooldown_sec: float = 25.0
    nudge_grace_sec: float = 15.0
    silence_probe_seq: int = 0          # Silence probes sent for current question (0=none yet; max 2).
    silence_probe_question: str = ""    # The question corresponding to the current follow-up question (changing the question means counting again)
    last_silence_probe: str = ""        # Content of the previous question (to avoid repeated questions)

    # ── Tips/Reports ─────────────────────────────
    hint_inflight: str | None = None
    report_task: asyncio.Task[Any] | None = None

    # ── Background tasks ────────────────────────────────
    bg_tasks: set[asyncio.Task[Any]] = field(default_factory=set)

    # ──TTS queue (injected by ws_handler)─────────────
    tts_queue: Any = None  # _SentenceTTSQueue, avoid circular import
