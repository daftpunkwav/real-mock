"""Prep session conversations: synchronous messages, SSE streaming, message history,
and context breakdown (with capability-token validation).

SSE streaming errors return only a redacted user-facing message; the original exception goes to logger.exception.
All operations here require the capability token issued at creation (``X-Interview-Token``).
History surgery (compact / summary / fork / truncate) lives in ``history.py``.

Usage envelopes: per-turn ``usage`` events carry provider-reported turn DELTAS
(frontend adds them up); the terminal ``done`` event and the non-streaming
response carry session-level totals (estimate + provider columns).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from realmock.domains.prep.agents.agent import PrepAgent
from realmock.domains.prep.agents.context import (
    BREAKDOWN_ORDER,
    build_context_breakdown,
)
from realmock.domains.prep.models import PrepSession
from realmock.domains.prep.routes.history import (
    _load_session_messages,
    _prune_dangling_tool_tail,  # noqa: F401  # backward-compatible re-export
)
from realmock.domains.prep.schemas import (
    PrepContextBucket,
    PrepContextResponse,
    PrepHistoryMessage,
    PrepMessageRequest,
    PrepMessageResponse,
)
from realmock.platform.capabilities.ai.context.options import CompactionOptions
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.capabilities.ai.llm.stream_filters import sanitize_special_tokens
from realmock.platform.core.constants import SessionStatus
from realmock.platform.core.errors import raise_error
from realmock.platform.core.security import redact_api_key
from realmock.platform.core.sse import format_sse_line, sse_error_event
from realmock.platform.core.session_auth import assert_session_token, extract_prep_token
from realmock.platform.database import get_api_db, get_sessions_db

logger = logging.getLogger(__name__)

# Redacted user-facing SSE error copy (upstream exception text is logged only).
_SSE_ERR_GENERIC = "Coaching response failed, please try again later"
_PREP_FORBIDDEN = "Don't have access to this coaching session"


def _build_prep_llm(api_db: Session, body: PrepMessageRequest) -> LLMClient:
    """Build per-request LLM client (optional profile_id/reasoning_effort override)."""
    return LLMClient.from_db(
        api_db,
        profile_id=body.model_profile_id,
        reasoning_effort=body.reasoning_effort,
    )


def _turn_policy(body: PrepMessageRequest) -> CompactionOptions:
    """Resolve turn compaction parameters (intensity/directive/retain)."""
    return CompactionOptions.resolve(
        intensity=body.compact_intensity,
        directive=body.compact_directive,
        retain=body.compact_retain,
    )


async def prep_message(
    session_id: int,
    body: PrepMessageRequest,
    db: Session = Depends(get_sessions_db),
    api_db: Session = Depends(get_api_db),
    access: str | None = Depends(extract_prep_token),
):
    """Run one synchronous coaching turn.

    Args:
        session_id: Target coaching session id.
        body: Validated turn parameters (content, model overrides, compaction policy).
        db: Sessions database session (injected).
        api_db: API database session for LLM profile lookup (injected).
        access: Capability token from header/cookie (injected).

    Returns:
        PrepMessageResponse with the reply, session usage totals, and backend-truth message count.

    Raises:
        ApiBusinessError: A3001 (missing session), A0401 (token mismatch), A3002 (completed).
    """
    session = db.query(PrepSession).filter(PrepSession.id == session_id).first()
    if not session:
        raise_error("A3001")
    assert_session_token(session, access, detail=_PREP_FORBIDDEN)
    if getattr(session, "status", None) == SessionStatus.COMPLETED.value:
        raise_error("A3002")
    llm = _build_prep_llm(api_db, body)
    agent = PrepAgent(session, llm)
    logger.info(
        "prep turn sid=%s model=%s window=%s profile_id=%s",
        session_id, llm.model, agent.context_window, body.model_profile_id,
    )
    reply = await agent.chat(
        body.content, db,
        drop_last_assistant=body.drop_last_assistant, ui_locale=body.ui_locale,
        context_session_ids=body.context_session_ids,
        compact_threshold=body.compact_threshold,
        compact_options=_turn_policy(body),
    )
    return PrepMessageResponse(
        reply=reply,
        token_usage=session.token_usage or 0,
        prompt_tokens=session.prompt_tokens or 0,
        completion_tokens=session.completion_tokens or 0,
        cached_tokens=session.cached_tokens or 0,
        prompt_tokens_estimated=agent.last_prompt_estimate,
        message_count=agent.last_message_count,
    )


async def prep_message_stream(
    session_id: int,
    body: PrepMessageRequest,
    request: Request,
    db: Session = Depends(get_sessions_db),
    api_db: Session = Depends(get_api_db),
    access: str | None = Depends(extract_prep_token),
):
    """Stream one coaching turn as server-sent events (tokens + status/thinking/tool/usage/done).

    Args:
        session_id: Target coaching session id.
        body: Validated turn parameters (same contract as the sync endpoint).
        request: Active request (used for client-disconnect detection).
        db: Sessions database session (injected).
        api_db: API database session for LLM profile lookup (injected).
        access: Capability token from header/cookie (injected).

    Returns:
        StreamingResponse with ``text/event-stream`` framing; failures surface
        as redacted ``error`` events (original exception is logged only).

    Raises:
        ApiBusinessError: A3001 (missing session), A0401 (token mismatch), A3002 (completed).
    """
    session = db.query(PrepSession).filter(PrepSession.id == session_id).first()
    if not session:
        raise_error("A3001")
    assert_session_token(session, access, detail=_PREP_FORBIDDEN)
    if getattr(session, "status", None) == SessionStatus.COMPLETED.value:
        raise_error("A3002")
    llm = _build_prep_llm(api_db, body)
    agent = PrepAgent(session, llm)
    logger.info(
        "prep stream turn sid=%s model=%s window=%s profile_id=%s",
        session_id, llm.model, agent.context_window, body.model_profile_id,
    )
    drop_last = body.drop_last_assistant
    ui_locale = body.ui_locale
    compact_threshold = body.compact_threshold
    turn_policy = _turn_policy(body)

    async def event_stream():
        try:
            async for chunk in agent.chat_stream(
                body.content, db, drop_last_assistant=drop_last, ui_locale=ui_locale,
                context_session_ids=body.context_session_ids,
                compact_threshold=compact_threshold,
                compact_options=turn_policy,
            ):
                # Stop button / closed tab: abandon the SSE body; the agent's
                # cancel path still persists the partial turn server-side.
                if await request.is_disconnected():
                    break
                if isinstance(chunk, dict):
                    # Structured events (such as search_results) generated by the Agent are directly transmitted transparently
                    event = chunk if chunk.get("type") else {"type": "token", "content": str(chunk)}
                    yield format_sse_line(event)
                else:
                    yield format_sse_line({"type": "token", "content": chunk})
            if await request.is_disconnected():
                return
            yield format_sse_line({
                "type": "done",
                "token_usage": session.token_usage,
                "prompt_tokens": session.prompt_tokens or 0,
                "completion_tokens": session.completion_tokens or 0,
                "cached_tokens": session.cached_tokens or 0,
                "prompt_tokens_estimated": agent.last_prompt_estimate,
                "turn_id": agent.last_turn_id or "",
                "prefix_fingerprint": agent.last_prefix_fingerprint or "",
                "message_count": agent.last_message_count,
            })
        except Exception as e:
            # Desensitization: Only write the original text of the log, and only return the general copy to the outside world
            safe_detail = redact_api_key(str(e)) or _SSE_ERR_GENERIC
            logger.exception("Prep streaming generation failed sid=%s: %s", session_id, safe_detail)
            yield format_sse_line(sse_error_event(e, message=_SSE_ERR_GENERIC))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def get_prep_messages(
    session_id: int,
    db: Session = Depends(get_sessions_db),
    access: str | None = Depends(extract_prep_token),
):
    """Return sanitized message history for display (store is never mutated).

    Args:
        session_id: Target coaching session id.
        db: Sessions database session (injected).
        access: Capability token from header/cookie (injected).

    Returns:
        Display-ready history (legacy template tokens stripped, null content coerced).

    Raises:
        ApiBusinessError: A3001 (missing session), A0401 (token mismatch).
    """
    session = db.query(PrepSession).filter(PrepSession.id == session_id).first()
    if not session:
        raise_error("A3001")
    assert_session_token(session, access, detail=_PREP_FORBIDDEN)
    messages = _load_session_messages(session)
    # Historical messages may contain leaked template tokens from before the
    # sanitizer was in place: clean before display without mutating the store.
    cleaned: list[dict[str, Any]] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        content = m.get("content")
        if not isinstance(content, str):
            # Loop-internal rows (assistant tool_calls with null content) predate
            # read-time coercion: normalize so the string contract holds and
            # history indices stay stable (tool_calls keys are kept for pairing).
            m["content"] = ""
        if m.get("role") == "assistant":
            m["content"] = sanitize_special_tokens(m["content"])
        cleaned.append(m)
    return [PrepHistoryMessage.model_validate(m) for m in cleaned]

def get_prep_context(
    session_id: int,
    db: Session = Depends(get_sessions_db),
    access: str | None = Depends(extract_prep_token),
):
    """Measured context breakdown of persisted history plus provider usage totals.

    Content-read path: requires the capability token. Bucket estimates use the
    same mechanical ratio as context budgeting; provider columns stay truthful
    (0 when the provider never reported) and the UI estimates the gap.

    Args:
        session_id: Target coaching session id.
        db: Sessions database session (injected).
        access: Capability token from header/cookie (injected).

    Returns:
        PrepContextResponse with per-bucket estimates plus provider totals.

    Raises:
        ApiBusinessError: A3001 (missing session), A0401 (token mismatch).
    """
    session = db.query(PrepSession).filter(PrepSession.id == session_id).first()
    if not session:
        raise_error("A3001")
    assert_session_token(session, access, detail=_PREP_FORBIDDEN)
    messages = _load_session_messages(session)
    counts = build_context_breakdown(messages)
    buckets = [PrepContextBucket(key=key, tokens=counts.get(key, 0)) for key in BREAKDOWN_ORDER]
    return PrepContextResponse(
        buckets=buckets,
        total_estimate=sum(counts.values()),
        prompt_tokens=session.prompt_tokens or 0,
        completion_tokens=session.completion_tokens or 0,
        cached_tokens=session.cached_tokens or 0,
    )

__all__ = [
    "get_prep_context",
    "get_prep_messages",
    "prep_message",
    "prep_message_stream",
]
