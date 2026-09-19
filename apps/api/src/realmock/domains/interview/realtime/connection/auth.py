"""WS connection authentication and business assembly (mixin): token verification, status check, pipe binding, opening/continuation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy.orm import Session

from realmock.platform.config import get_settings
from realmock.platform.core.constants import SessionStatus
from realmock.platform.core.session_auth import tokens_match
from realmock.platform.database import api_db_session
from realmock.domains.interview.agents import (
    session_llm,
    session_stt_credentials,
    session_tts_credentials,
    voice_prompt_directive,
)
from realmock.domains.interview.models import InterviewSession
from realmock.domains.interview.realtime.core.events import TurnState
from realmock.domains.interview.realtime.core.session_registry import claim_session_connection
from realmock.domains.interview.agents import InterviewRunner, InterviewSessionState
from realmock.platform.capabilities.voice.stt import is_local_stt_model, warmup_whisper
from realmock.platform.capabilities.voice.tts.voice_resolve import VoiceProsody, resolve_prosody
from realmock.platform.capabilities.voice.config.catalog import find_provider

if TYPE_CHECKING:
    import asyncio
    from collections.abc import AsyncIterator, Callable, Coroutine

    from realmock.domains.interview.agents.events import StreamEvent
    from realmock.domains.interview.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)


class ConnectionAuthMixin:
    """Auth / session bind / pipeline assembly; depends on ctx fields plus send / set_turn / _spawn."""

    ctx: "ConnectionContext"

    if TYPE_CHECKING:
        # Members provided by sibling mixins / the composed InterviewWSHandler.
        _superseded: bool

        @property
        def session_id(self): ...

        @property
        def ws(self): ...

        send: Callable[..., Coroutine[Any, Any, None]]
        _fail_and_close: Callable[..., Coroutine[Any, Any, None]]
        _spawn: Callable[..., "asyncio.Task[Any]"]
        set_turn: Callable[[TurnState], Coroutine[Any, Any, None]]
        _mark_tts_sent: Callable[..., None]
        _tts_send: Callable[..., Coroutine[Any, Any, None]]
        _stream_events_with_tts: Callable[..., Coroutine[Any, Any, StreamEvent | None]]
        _consume_runner_opening: Callable[..., "AsyncIterator[StreamEvent]"]
        _open_mic_after_playback: Callable[..., Coroutine[Any, Any, None]]
        _begin_playback_wait: Callable[..., None]
        arm_think_timer: Callable[..., None]

    # ------------------------------------------------------------------
    # Authentication and session checking
    # ------------------------------------------------------------------

    async def authenticate(
        self, db: Session
    ) -> InterviewSession | None:
        """Validate session existence, access token, and status; claim the single-connection lease on success.

        Returns:
            The validated session; on failure an error was already sent and the socket closed, so None.
        """
        session = db.query(InterviewSession).filter(
            InterviewSession.id == self.ctx.session_id
        ).first()
        if not session:
            await self._fail_and_close("Interview session does not exist")
            return None
        if not tokens_match(
            getattr(session, "access_token", None), self.ctx.client_access_token
        ):
            await self._fail_and_close("Don't have access to this interview session")
            return None
        if session.status not in (SessionStatus.PENDING.value, SessionStatus.ACTIVE.value):
            await self._fail_and_close("The interview has ended")
            return None
        await claim_session_connection(self)
        return session

    # ------------------------------------------------------------------
    # LLM / RAG / Voice Pipe Assembly
    # ------------------------------------------------------------------

    async def bind_pipeline(
        self, db: Session, session: InterviewSession
    ) -> bool:
        """Assemble LLM, Agent, Runner, STT/TTS credentials, and voice.

        Returns:
            True when assembly succeeds; on failure an error was already sent and the socket closed, so False.
        """
        with api_db_session() as api_db:
            self.ctx.llm = session_llm(api_db, session)
            if not self.ctx.llm.api_key:
                await self._fail_and_close("Please configure the API Key of the interview thinking processor first")
                return False
            self.ctx.stt_creds = session_stt_credentials(api_db, session)
            self.ctx.tts_creds = session_tts_credentials(api_db, session)
        self.ctx.agent = InterviewSessionState(
            session,
            self.ctx.llm,
            voice_directive=voice_prompt_directive(self.ctx.tts_creds),
        )
        self.ctx.reference_detail = getattr(session, "reference_detail", None) or "outline"

        rag = None
        try:
            # Function-level import: RAG is optional — an import-time failure
            # must degrade to RAG-less mode here, not break pipeline assembly.
            from realmock.domains.interview.capabilities.rag.company_rag import CompanyKnowledgeRAG

            rag = CompanyKnowledgeRAG(self.ctx.llm)
        except Exception as e:
            logger.warning("RAG instantiation failed, continue in RAG-less mode: %s", e)

        self.ctx.runner = InterviewRunner(
            session, self.ctx.llm, self.ctx.agent, rag=rag, task_spawner=self._spawn
        )

        cfg = get_settings()
        settings_voice = self.ctx.tts_creds.voice or cfg.tts_voice
        self.ctx.tts_voice = settings_voice
        self.ctx.whisper_model = self.ctx.stt_creds.model or cfg.whisper_model
        await self._announce_fallbacks()

        await self._bind_prosody()
        await self._warmup_stt()
        return True

    async def _announce_fallbacks(self) -> None:
        """Notify the client when a provider is coming_soon and a runtime fallback is used."""
        rec_meta = find_provider("recognize", self.ctx.stt_creds.provider)
        if rec_meta and rec_meta.get("status") == "coming_soon":
            await self.send(
                "info",
                message=(
                    f"Speech recognition provider '{rec_meta.get('label')}' is not wired yet; "
                    "falling back to local Whisper transcription."
                ),
            )
        speak_meta = find_provider("speak", self.ctx.tts_creds.handler)
        if speak_meta and speak_meta.get("status") == "coming_soon":
            await self.send(
                "info",
                message=(
                    f"Speech synthesis provider '{speak_meta.get('label')}' is not wired yet; "
                    "falling back to Edge TTS."
                ),
            )
        if self.ctx.tts_creds.mode == "text_only" or self.ctx.tts_creds.handler == "none":
            await self.send("info", message="Captions-only mode enabled; speech playback is off")

    async def _bind_prosody(self) -> None:
        """Analyze timbres by session persona/avatar and bind TTS queue."""
        # bind_pipeline assigns ctx.agent before calling this method.
        agent_session = cast("InterviewSessionState", self.ctx.agent).session
        self.ctx.session_prosody = resolve_prosody(
            avatar_id=getattr(agent_session, "avatar_id", None),
            personality=getattr(agent_session, "personality", None),
            strictness=getattr(agent_session, "strictness", None),
            emotion=None,
            llm_settings_voice=self.ctx.tts_creds.voice or self.ctx.tts_voice,
            handler=self.ctx.tts_creds.handler,
        )
        if self.ctx.tts_creds.handler not in ("edge", "minimax_speech", "none"):
            self.ctx.session_prosody = VoiceProsody(
                voice=self.ctx.tts_creds.voice or self.ctx.tts_voice or "mimo_default",
                rate=self.ctx.session_prosody.rate,
                pitch=self.ctx.session_prosody.pitch,
            )
        self.ctx.tts_voice = self.ctx.session_prosody.voice
        self.ctx.tts_creds.voice = self.ctx.tts_voice
        self.ctx.tts_queue.set_prosody(self.ctx.session_prosody)
        self.ctx.tts_queue.set_tts_creds(self.ctx.tts_creds)
        self.ctx.tts_queue.set_on_sent(self._mark_tts_sent)
        logger.info(
            "pipeline bound sid=%s asr=%s speak=%s voice=%s rate=%s pitch=%s",
            self.ctx.session_id,
            self.ctx.stt_creds.provider,
            self.ctx.tts_creds.handler,
            self.ctx.session_prosody.voice,
            self.ctx.session_prosody.rate,
            self.ctx.session_prosody.pitch,
        )

    async def _warmup_stt(self) -> None:
        """Pre-warm local Whisper (configured model, else base) in background."""
        if self.ctx.stt_creds.provider == "local" or is_local_stt_model(self.ctx.whisper_model):
            local_m = self.ctx.whisper_model if is_local_stt_model(self.ctx.whisper_model) else "base"
            self._spawn(warmup_whisper(local_m))
        else:
            self._spawn(warmup_whisper("base"))

    # ------------------------------------------------------------------
    # Advance after connection is established (opening/continuation)
    # ------------------------------------------------------------------

    def rebind_runtime_session(self, session: InterviewSession) -> None:
        """Rebind the session object held by runner/agent to this turn's DB-attached instance.

        ``bind_pipeline`` builds runner/agent from the main-loop DB session. Turn paths open a
        short-lived DB afterward; mutating the original (detached) object will not persist via
        this turn's ``save_state`` (observed: turn state lost). Every turn/closing entry that
        loads a session must call this first so state changes flush with this turn's DB.
        """
        if self.ctx.agent is not None:
            self.ctx.agent.session = session
        if self.ctx.runner is not None:
            self.ctx.runner.session = session
            self.ctx.runner.agent.session = session
            self.ctx.runner.prompter.session = session
            self.ctx.runner.tools.session = session

    async def start_session_flow(self, session: InterviewSession, db: Session) -> None:
        """PENDING opening statement; ACTIVE waiting for the candidate to continue."""
        if session.status == SessionStatus.PENDING.value:
            await self.ctx.tts_queue.start(self._tts_send)
            await self.set_turn(TurnState.AI_SPEAKING)
            await self._stream_events_with_tts(
                self._consume_runner_opening(db),
                db=db,
                session=session,
                auto_hint=True,
            )
            await self._open_mic_after_playback()
        elif session.status == SessionStatus.ACTIVE.value:
            await self.ctx.tts_queue.start(self._tts_send)
            self._begin_playback_wait()
            self.ctx.tts_sent_this_turn = False
            await self.set_turn(TurnState.USER_SPEAKING)
            # Refresh/reconnect resume: this is a fresh connection context, so
            # the server-owned think window is gone. Re-arm it here, or a
            # candidate who reconnects and then goes silent gets no follow-up
            # until the next completed exchange (probe pipeline is capped, so
            # this cannot loop).
            self.arm_think_timer()


__all__ = ["ConnectionAuthMixin"]
