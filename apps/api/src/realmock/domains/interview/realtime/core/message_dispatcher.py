"""WS inbound message dispatch (mixin): audio_chunk / stt_text / user_turn_end / various requests."""

from __future__ import annotations

import asyncio
import base64
import logging
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from realmock.domains.interview.capabilities.vision.agent import VisionAgent
from realmock.domains.interview.models import InterviewSession
from realmock.domains.interview.realtime.core.events import TurnState
from realmock.platform.core import constants as _platform_constants
from realmock.platform.core.constants import DEFAULT_LLM_RATE_LIMIT_PER_MINUTE, MAX_USER_TEXT_CHARS
from realmock.platform.core.ratelimit import try_rate_limit_by_id

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine, Mapping

    from realmock.domains.interview.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)

# Single source: canonical value lives in platform.core.constants; this alias
# keeps the historic module name (ws_handler re-exports it and tests pin it).
AUDIO_BUFFER_MAX_BYTES: int = _platform_constants.AUDIO_BUFFER_MAX_BYTES
_WS_LLM_RATE_LIMIT = DEFAULT_LLM_RATE_LIMIT_PER_MINUTE
# Whiteboard code mirror cap: ~100x a normal interview snippet; beyond this
# the frame is pathological (stuck client / fuzzer), not an interview answer.
_CODING_CODE_MAX_CHARS = 200_000


class MessageDispatcherMixin:
    """Distributed by message type; relies on ctx field and _spawn/send/set_turn."""

    ctx: "ConnectionContext"

    if TYPE_CHECKING:
        # Members provided by sibling mixins of the composed InterviewWSHandler.
        send: Callable[..., Coroutine[Any, Any, None]]
        _spawn: Callable[..., "asyncio.Task[Any]"]
        mark_answer_started: Callable[..., None]
        _can_start_user_turn: Callable[..., bool]
        _run_user_turn_end: Callable[..., Coroutine[Any, Any, None]]
        _on_silence_nudge: Callable[..., Coroutine[Any, Any, None]]
        _on_candidate_barge_in: Callable[..., Coroutine[Any, Any, None]]
        _hint_rate_limited: Callable[..., Coroutine[Any, Any, None]]
        _on_request_hint: Callable[..., Coroutine[Any, Any, None]]
        _on_request_finish: Callable[..., Coroutine[Any, Any, None]]
        _run_user_text: Callable[..., Coroutine[Any, Any, None]]

    def _llm_rate_limited(self, *, limit: int) -> bool:
        if not try_rate_limit_by_id(
            key="llm",
            client_id=f"ws-{self.ctx.session_id}",
            limit=limit,
        ):
            return True
        return False

    # Message type -> admission wrapper name on the composed handler.
    # Table-driven dispatch keeps the branch list flat; unknown types warn.
    # Wrappers use the ``_start_*`` prefix to stay distinct from the ``_on_*``
    # turn workers they spawn (e.g. ``_start_user_turn_end`` vs ``_on_user_turn_end``).
    # The mapping is immutable so a subclass cannot corrupt dispatch for siblings.
    _MESSAGE_HANDLER_NAMES: "Mapping[str, str]" = MappingProxyType(
        {
            # audio_chunk is a reserved legacy inbound (no first-party
            # sender; voice travels as PCM inside user_turn_end).
            "audio_chunk": "_on_audio_chunk",
            "stt_text": "_on_stt_text",
            "user_typing": "_on_user_typing",
            "pong": "_on_pong",
            "vision_update": "_on_vision_update",
            "user_turn_end": "_start_user_turn_end",
            "silence_timeout": "_on_silence_timeout",
            "barge_in": "_on_barge_in",
            "user_text": "_on_user_text",
            "request_hint": "_start_request_hint",
            "request_finish": "_start_request_finish",
            "tts_playback_done": "_on_tts_playback_done",
            "coding_code_update": "_on_coding_code_update",
            "coding_run_request": "_on_coding_run_request",
            "coding_submit_request": "_on_coding_submit_request",
        }
    )

    async def _dispatch(
        self,
        data: dict[str, Any],
        db: Session | None = None,
        session: InterviewSession | None = None,
    ) -> None:
        """Distributed by message type; the round path builds a short life cycle db by itself, and this method does not use db/session."""
        msg_type = data.get("type", "")
        handler_name = self._MESSAGE_HANDLER_NAMES.get(msg_type)
        if handler_name is None:
            logger.warning("Unknown WS message type sid=%s type=%s", self.ctx.session_id, msg_type)
            return
        handler = getattr(self, handler_name, None)
        if handler is None:
            logger.warning(
                "Dispatch table points to missing handler sid=%s type=%s name=%s",
                self.ctx.session_id,
                msg_type,
                handler_name,
            )
            return
        await handler(data)

    async def _on_stt_text(self, data: dict[str, Any]) -> None:
        # Inbound frames are untrusted: a non-string text (null/number) must not
        # raise inside the dispatch loop.
        text = str(data.get("text") or "").strip()
        if len(text) > MAX_USER_TEXT_CHARS:
            # Interim partials are superseded by the next frame; drop the
            # pathological one instead of echoing megabytes back.
            logger.debug(
                "stt_text overlong session=%s len=%d", self.ctx.session_id, len(text)
            )
            return
        if text:
            # Voice partials count as "the candidate started answering": the
            # think window ends and the answer window takes over.
            self.mark_answer_started()
            await self.send("stt_partial", text=text)

    async def _on_user_typing(self, data: dict[str, Any]) -> None:
        """Typing uplink (client-throttled): first keystroke ends the think window."""
        del data
        self.mark_answer_started()

    async def _on_pong(self, data: dict[str, Any]) -> None:
        del data

    async def _on_vision_update(self, data: dict[str, Any]) -> None:
        face = data.get("face_analysis")
        if face:
            self.ctx.orchestrator.snapshot.merge_face(face)
            self.ctx.orchestrator.snapshot.vision_summary = VisionAgent.summarize(face)

    async def _start_user_turn_end(self, data: dict[str, Any]) -> None:
        if self.ctx.closing:
            return
        if not self._can_start_user_turn():
            logger.info(
                "user_turn_end busy sid=%s turn_busy=%s busy_epoch=%s stream_epoch=%s",
                self.ctx.session_id,
                self.ctx.turn_busy,
                self.ctx.busy_epoch,
                self.ctx.stream_epoch,
            )
            await self.send(
                "info",
                message="The interviewer is still responding to the previous turn; please wait a moment",
            )
            return
        if self._llm_rate_limited(limit=_WS_LLM_RATE_LIMIT):
            await self._send_rate_limited()
            return
        self._spawn(self._run_user_turn_end(data))

    async def _on_silence_timeout(self, data: dict[str, Any]) -> None:
        del data
        if self.ctx.turn_busy or self.ctx.closing:
            return
        self._spawn(self._on_silence_nudge())

    async def _on_barge_in(self, data: dict[str, Any]) -> None:
        del data
        if self.ctx.closing:
            return
        self._spawn(self._on_candidate_barge_in())

    async def _start_request_hint(self, data: dict[str, Any]) -> None:
        if self._llm_rate_limited(limit=max(5, _WS_LLM_RATE_LIMIT // 2)):
            # Terminal event (not the generic error): the room clears its
            # loading state instead of hanging until the client timeout.
            await self._hint_rate_limited(data)
            return
        self._spawn(self._on_request_hint(data))

    async def _start_request_finish(self, data: dict[str, Any]) -> None:
        del data
        if self.ctx.closing:
            return
        self._spawn(self._on_request_finish())

    async def _on_tts_playback_done(self, data: dict[str, Any]) -> None:
        client_gen = data.get("generation")
        if client_gen is None or client_gen == self.ctx.awaiting_playback_gen:
            self.ctx.playback_done.set()
            # The interviewer's voice just finished: silence timing starts here.
            self.ctx.speech_end_at = asyncio.get_event_loop().time()

    async def _send_rate_limited(self) -> None:
        await self.send(
            "error",
            message="Too many requests, please try again later",
            code="A0002",
            retryable=True,
        )

    async def _on_audio_chunk(self, data: dict[str, Any]) -> None:
        chunk = data.get("data", "")
        if not chunk:
            return
        if not isinstance(chunk, str):
            # A non-string element would poison the buffer: stt_finish joins
            # it with "".join. Drop instead of crashing the turn later.
            logger.debug(
                "audio_chunk non-string session=%s type=%s",
                self.ctx.session_id,
                type(chunk).__name__,
            )
            return
        # Pre-check before decoding: base64 inflates ~4/3, so a frame that
        # alone exceeds the budget is rejected without paying decode cost.
        if self.ctx.audio_buffer_bytes + (len(chunk) * 3 // 4) > AUDIO_BUFFER_MAX_BYTES:
            await self._reject_audio_overflow()
            return
        try:
            new_bytes = len(base64.b64decode(chunk, validate=False))
        except (ValueError, TypeError):
            logger.debug(
                "audio_chunk not base64 session=%s", self.ctx.session_id, exc_info=True
            )
            new_bytes = 0
        if self.ctx.audio_buffer_bytes + new_bytes > AUDIO_BUFFER_MAX_BYTES:
            await self._reject_audio_overflow()
            return
        self.ctx.audio_buffer.append(chunk)
        self.ctx.audio_buffer_bytes += new_bytes

    async def _reject_audio_overflow(self) -> None:
        logger.warning(
            "audio_buffer exceeds the upper limit session=%s bytes=%s",
            self.ctx.session_id,
            self.ctx.audio_buffer_bytes,
        )
        await self.send(
            "error",
            message="Audio buffer exceeded; end the current turn first",
            code="A0004",
        )
        self.ctx.audio_buffer = []
        self.ctx.audio_buffer_bytes = 0

    async def _on_user_text(self, data: dict[str, Any]) -> None:
        text = str(data.get("text") or "").strip()
        if len(text) > MAX_USER_TEXT_CHARS:
            await self.send(
                "error",
                message=f"Text too long (limit: {MAX_USER_TEXT_CHARS} characters)",
                code="A0003",
            )
            return
        if not text or self.ctx.closing:
            return
        if (
            self.ctx.turn_state != TurnState.USER_SPEAKING
            or not self._can_start_user_turn()
        ):
            # Never drop silently: the client cleared its input on send, so a
            # quiet drop looks like "sent but the interviewer never replies"
            # and the next message appears to "unblock" it. A light info toast
            # tells the candidate to wait instead of resending.
            logger.info(
                "user_text dropped sid=%s state=%s turn_busy=%s busy_epoch=%s stream_epoch=%s len=%d",
                self.ctx.session_id,
                self.ctx.turn_state,
                self.ctx.turn_busy,
                self.ctx.busy_epoch,
                self.ctx.stream_epoch,
                len(text),
            )
            await self.send(
                "info",
                message="The interviewer is still responding to the previous turn; please wait a moment",
            )
            return
        if self._llm_rate_limited(limit=_WS_LLM_RATE_LIMIT):
            await self._send_rate_limited()
            return
        self._spawn(self._run_user_text(text, data))

    async def _on_coding_code_update(self, data: dict[str, Any]) -> None:
        try:
            code = str(data.get("code", ""))
            if len(code) > _CODING_CODE_MAX_CHARS:
                # Keep the last good mirror instead of caching a pathological
                # payload in working memory.
                logger.debug(
                    "coding_code_update overlong session=%s len=%d",
                    self.ctx.session_id,
                    len(code),
                )
                return
            runner = getattr(self.ctx, "runner", None)
            agent = getattr(runner, "agent", None) if runner else None
            cog_mem = getattr(agent, "cognitive_memory", None) if agent else None
            wm = getattr(cog_mem, "working_memory", None) if cog_mem else None
            if wm is not None:
                wm.candidate_code = code
        except Exception as exc:
            logger.warning("Failed to update candidate code in working memory: %s", exc)

    async def _on_coding_run_request(self, data: dict[str, Any]) -> None:
        try:
            code = str(data.get("code", ""))
            raw_output = str(data.get("test_output", "Tests run locally in browser sandbox."))
            if len(code) > _CODING_CODE_MAX_CHARS or len(raw_output) > _CODING_CODE_MAX_CHARS:
                await self.send(
                    "error",
                    message=(
                        f"Code or test output too long (limit: {_CODING_CODE_MAX_CHARS} characters); "
                        "shrink it and retry"
                    ),
                    code="A0003",
                )
                return
            runner = getattr(self.ctx, "runner", None)
            if not runner or not hasattr(runner, "coding_examiner"):
                return
            challenge = runner.coding_examiner.active_challenge
            test_cases = [tc.to_dict() for tc in challenge.test_cases] if challenge else []
            from realmock.domains.interview.capabilities.sandbox.evaluator import evaluate_test_cases
            outcome = evaluate_test_cases(
                test_cases=test_cases,
                candidate_code=code,
                raw_output=raw_output,
            )
            await self.send("coding_test_result", **outcome.to_dict())
        except Exception as exc:
            logger.warning("Failed to process coding run request: %s", exc)

    async def _on_coding_submit_request(self, data: dict[str, Any]) -> None:
        try:
            code = str(data.get("code", ""))
            test_output = str(data.get("test_output", ""))
            if len(code) > _CODING_CODE_MAX_CHARS or len(test_output) > _CODING_CODE_MAX_CHARS:
                await self.send(
                    "error",
                    message=(
                        f"Code or test output too long (limit: {_CODING_CODE_MAX_CHARS} characters); "
                        "shrink it and retry"
                    ),
                    code="A0003",
                )
                return
            runner = getattr(self.ctx, "runner", None)
            if not runner or not hasattr(runner, "coding_examiner"):
                return
            agent = getattr(runner, "agent", None)
            turn_index = len(agent.agent_state.get("asked_questions", [])) if agent and hasattr(agent, "agent_state") else 0
            # Bounded so one slow LLM evaluation cannot hold the WS message
            # loop (and with it user_text/playback_done) for minutes.
            report = await asyncio.wait_for(
                runner.coding_examiner.evaluate_submission(
                    code=code,
                    test_output=test_output,
                    turn_index=turn_index,
                ),
                timeout=90.0,
            )
            await self.send("coding_eval_report", report=report.to_dict())
        except asyncio.TimeoutError:
            logger.warning(
                "coding submit evaluation timed out sid=%s", self.ctx.session_id
            )
            await self.send(
                "error",
                message="Code evaluation timed out; please try again later",
                code="C0001",
                retryable=True,
            )
        except Exception as exc:
            logger.warning("Failed to process coding submit request: %s", exc)
            await self.send(
                "error",
                message="Code evaluation failed; please try again later",
                code="C0001",
                retryable=True,
            )


__all__ = ["MessageDispatcherMixin", "AUDIO_BUFFER_MAX_BYTES"]
