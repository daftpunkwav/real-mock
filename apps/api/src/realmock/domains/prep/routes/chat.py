"""Prep session conversations: synchronous messages, SSE streaming, message history,
and context breakdown (with capability-token validation).

SSE streaming errors surface verbatim provider text only for user-actionable
upstream classes (quota exhausted / rate limited / context overflow), secret-
redacted and length-capped; every other failure falls back to the generic copy
while the original exception goes to logger.exception.
All operations here require the capability token issued at creation (``X-Interview-Token``).
Turns are serialized per session (``services.turn_lock``): a queued request
reloads the committed history inside the lock instead of acting on the
snapshot it took while waiting.
History surgery (compact / summary / fork / truncate) lives in ``history.py``.

Usage envelopes: per-turn ``usage`` events carry provider-reported turn DELTAS
(frontend adds them up); the terminal ``done`` event and the non-streaming
response carry session-level totals (estimate + provider columns).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from realmock.domains.prep.agents.agent import PrepAgent
from realmock.domains.prep.agents.context import (
    BREAKDOWN_ORDER,
    build_context_breakdown,
)
from realmock.domains.prep.routes.history import (
    _load_session_messages,
    _prune_dangling_tool_tail,  # noqa: F401  # backward-compatible re-export
)
from realmock.domains.prep.schemas import (
    PrepAskEvent,
    PrepContextBucket,
    PrepContextResponse,
    PrepHistoryMessage,
    PrepMessageRequest,
    PrepMessageResponse,
    PrepSuggestionsRequest,
    PrepSuggestionsResponse,
)
from realmock.domains.prep.services import (
    require_open_prep_session,
    require_owned_prep_session,
    require_writable_prep_session,
    session_turn_lock,
)
from realmock.platform.capabilities.ai.context.options import CompactionOptions
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.capabilities.ai.llm.provider_errors import is_diagnosable_upstream_error
from realmock.platform.capabilities.ai.llm.stream_filters import sanitize_special_tokens
from realmock.platform.core.security import redact_secrets_in_text
from realmock.platform.core.session_auth import extract_prep_token
from realmock.platform.core.sse import (
    QueuePut,
    pump_queue_to_sse,
    sse_error_event,
    sse_streaming_response,
)
from realmock.platform.database import get_api_db, get_sessions_db

logger = logging.getLogger(__name__)

# Redacted user-facing SSE error copy (upstream exception text is logged only).
_SSE_ERR_GENERIC = "Coaching response failed, please try again later"
# Verbatim provider text is length-capped like other model-facing observations.
_SSE_DETAIL_MAX_CHARS = 400
# Keep-alive interval for the coaching stream. A turn can sit silent for
# minutes while the provider generates (one LLM call is budgeted at up to
# 300 s, and the shared retry ladder adds more), so the stream must prove
# liveness on its own: the browser client aborts a coaching stream after
# 120 s without a byte and would otherwise drop a turn that is merely slow.
# 15 s matches the resume deep-review stream and stays far below that
# client-side budget.
_SSE_HEARTBEAT_SECONDS = 15.0


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
    """Run one synchronous coaching turn."""
    # Admit the session before the turn starts: an unknown session, a wrong
    # capability token, or a completed session must answer with an HTTP
    # error, not with a model observation.
    require_open_prep_session(db, session_id, access)
    llm = _build_prep_llm(api_db, body)
    # One turn at a time per session: concurrent requests would each load the
    # same history and save last-writer-wins, silently dropping a turn.
    async with session_turn_lock(session_id):
        # A queued request may have loaded its session snapshot before the
        # previous turn committed: drop the identity map so the agent reads
        # the freshly saved history, and revalidate existence/status.
        db.expire_all()
        session = require_writable_prep_session(db, session_id)
        agent = PrepAgent(session, llm)
        logger.info(
            "prep turn sid=%s model=%s window=%s profile_id=%s",
            session_id,
            llm.model,
            agent.context_window,
            body.model_profile_id,
        )
        agent.memory_index_limit = body.memory_index_limit
        reply = await agent.chat(
            body.content,
            db,
            drop_last_assistant=body.drop_last_assistant,
            ui_locale=body.ui_locale,
            context_session_ids=body.context_session_ids,
            compact_threshold=body.compact_threshold,
            compact_options=_turn_policy(body),
            memory_index_limit=body.memory_index_limit,
        )
    return PrepMessageResponse(
        reply=reply,
        # Dialog awaiting the user's answer when the turn ended on ask_user.
        ask_user=(
            PrepAskEvent.model_validate(agent.last_ask_event)
            if isinstance(agent.last_ask_event, dict)
            else None
        ),
        token_usage=session.token_usage or 0,
        prompt_tokens=session.prompt_tokens or 0,
        completion_tokens=session.completion_tokens or 0,
        cached_tokens=session.cached_tokens or 0,
        last_round_prompt_tokens=session.last_round_prompt_tokens or 0,
        last_round_completion_tokens=session.last_round_completion_tokens or 0,
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
    """Stream one coaching turn as server-sent events (tokens + status/thinking/tool/usage/done)."""
    # Admit the session before the stream opens: a rejected session must
    # answer with an HTTP error, not with an SSE error frame.
    require_open_prep_session(db, session_id, access)
    llm = _build_prep_llm(api_db, body)
    drop_last = body.drop_last_assistant
    ui_locale = body.ui_locale
    compact_threshold = body.compact_threshold
    turn_policy = _turn_policy(body)

    async def produce(put: QueuePut) -> None:
        """Run the turn and push its events; the pump owns the keep-alive and the disconnect check."""
        usage_acc = getattr(llm, "usage", None)
        try:
            # One turn at a time per session (see prep_message): the agent is
            # constructed inside the lock, after dropping this request's
            # identity map so a queued request reads the freshly saved
            # history instead of its pre-wait snapshot.
            async with session_turn_lock(session_id):
                db.expire_all()
                session = require_writable_prep_session(db, session_id)
                agent = PrepAgent(session, llm)
                logger.info(
                    "prep stream turn sid=%s model=%s window=%s profile_id=%s",
                    session_id,
                    llm.model,
                    agent.context_window,
                    body.model_profile_id,
                )
                agent.memory_index_limit = body.memory_index_limit
                async for chunk in agent.chat_stream(
                    body.content,
                    db,
                    drop_last_assistant=drop_last,
                    ui_locale=ui_locale,
                    context_session_ids=body.context_session_ids,
                    compact_threshold=compact_threshold,
                    compact_options=turn_policy,
                    memory_index_limit=body.memory_index_limit,
                ):
                    # Structured events (such as search_results) generated by the Agent are directly transmitted transparently
                    if isinstance(chunk, dict):
                        event = (
                            chunk if chunk.get("type") else {"type": "token", "content": str(chunk)}
                        )
                    else:
                        event = {"type": "token", "content": chunk}
                    await put(event)
                await put(
                    {
                        "type": "done",
                        "token_usage": session.token_usage,
                        "prompt_tokens": session.prompt_tokens or 0,
                        "completion_tokens": session.completion_tokens or 0,
                        "cached_tokens": session.cached_tokens or 0,
                        "last_round_prompt_tokens": session.last_round_prompt_tokens or 0,
                        "last_round_completion_tokens": session.last_round_completion_tokens or 0,
                        "prompt_tokens_estimated": agent.last_prompt_estimate,
                        "turn_id": agent.last_turn_id or "",
                        "prefix_fingerprint": agent.last_prefix_fingerprint or "",
                        "message_count": agent.last_message_count,
                        # Turn-level request diagnostics. ``last_*`` are latest-wins;
                        # ``requests``/``reasoning_tokens`` deliberately absent — the
                        # per-turn values ride the ``usage`` event instead (this
                        # envelope's token columns are session totals, so a per-turn
                        # count would be misread as one and clobber accumulation).
                        "last_request_id": getattr(usage_acc, "last_request_id", "") or "",
                        "last_latency_ms": getattr(usage_acc, "last_latency_ms", 0.0) or 0.0,
                    }
                )
        except Exception as e:
            # Only provider conditions the user can act on (quota exhausted,
            # rate limited, context overflow) surface their verbatim text so
            # the cause is diagnosable; every other failure class (auth,
            # gateway, SDK internals) falls back to the generic copy — raw
            # upstream traces may carry internal URLs or header fragments.
            # Embedded credentials are masked either way.
            if is_diagnosable_upstream_error(e):
                safe_detail = (
                    redact_secrets_in_text(str(e))[:_SSE_DETAIL_MAX_CHARS] or _SSE_ERR_GENERIC
                )
            else:
                safe_detail = _SSE_ERR_GENERIC
            logger.exception("Prep streaming generation failed sid=%s: %s", session_id, safe_detail)
            await put(sse_error_event(e, message=safe_detail))
        finally:
            # End the stream. The pump drops whatever is still queued once the
            # client is gone, so the sentinel is a no-op in that case.
            await put(None)

    return sse_streaming_response(
        pump_queue_to_sse(request, produce, heartbeat_seconds=_SSE_HEARTBEAT_SECONDS)
    )


def get_prep_messages(
    session_id: int,
    db: Session = Depends(get_sessions_db),
    access: str | None = Depends(extract_prep_token),
):
    """Return sanitized message history for display (store is never mutated)."""
    session = require_owned_prep_session(db, session_id, access)
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
    """Measured context breakdown of persisted history plus provider usage totals."""
    session = require_owned_prep_session(db, session_id, access)
    messages = _load_session_messages(session)
    counts = build_context_breakdown(messages)
    buckets = [PrepContextBucket(key=key, tokens=counts.get(key, 0)) for key in BREAKDOWN_ORDER]
    return PrepContextResponse(
        buckets=buckets,
        total_estimate=sum(counts.values()),
        prompt_tokens=session.prompt_tokens or 0,
        completion_tokens=session.completion_tokens or 0,
        cached_tokens=session.cached_tokens or 0,
        last_round_prompt_tokens=session.last_round_prompt_tokens or 0,
        last_round_completion_tokens=session.last_round_completion_tokens or 0,
    )


# Suggestions are a nicety: one cheap JSON call, short budget, and any failure
# degrades to an empty list (the UI keeps its default prompts) instead of an error.
_SUGGESTIONS_TIMEOUT_SECONDS = 20.0
_SUGGESTION_MAX_CHARS = 60
_SUGGESTIONS_PROMPT = (
    "You generate follow-up question suggestions for an interview-prep chat. "
    "Based on the user's last message and the assistant's latest reply below, propose "
    "exactly 4 short, specific questions the user would most likely ask next. "
    "Write the questions in {locale_name}. Each stays under 40 characters, is "
    "self-contained, and ends with a question mark. No numbering, no quotes, "
    "no commentary.\n\n"
    'Return JSON: {{"suggestions": ["...", "...", "...", "..."]}}\n\n'
    "User's last message:\n{user_text}\n\n"
    "Assistant's latest reply:\n{reply}"
)


def _locale_label(ui_locale: str | None) -> str:
    return "Simplified Chinese (zh-CN)" if (ui_locale or "").lower().startswith("zh") else "English"


def _last_exchange(messages: list[dict[str, Any]]) -> tuple[str, str] | None:
    """Latest (user text, assistant reply) pair; None when history has none."""
    reply = ""
    user_text = ""
    for message in reversed(messages):
        if not isinstance(message, dict):
            continue
        content = str(message.get("content") or "").strip()
        if not content:
            continue
        role = message.get("role")
        if role == "assistant" and not reply:
            reply = content
        elif role == "user" and reply:
            user_text = content
            break
    if not user_text or not reply:
        return None
    return user_text[-2000:], reply[-4000:]


async def suggest_prep_followups(
    session_id: int,
    db: Session = Depends(get_sessions_db),
    api_db: Session = Depends(get_api_db),
    body: PrepSuggestionsRequest | None = None,
    access: str | None = Depends(extract_prep_token),
):
    """AI follow-up suggestions for the quick-prompts card (best-effort)."""
    session = require_owned_prep_session(db, session_id, access)
    params = body or PrepSuggestionsRequest()
    exchange = _last_exchange(_load_session_messages(session))
    if exchange is None:
        return PrepSuggestionsResponse()
    user_text, reply = exchange
    # Thinking is disabled: a reasoning model would burn the short budget on
    # deliberation and always blow the timeout, leaving the card frozen on
    # its default prompts.
    llm = LLMClient.from_db(
        api_db,
        profile_id=params.model_profile_id,
        enable_thinking=False,
    )
    prompt = _SUGGESTIONS_PROMPT.format(
        locale_name=_locale_label(params.ui_locale),
        user_text=user_text,
        reply=reply,
    )
    try:
        verdict = await asyncio.wait_for(
            llm.chat_json([{"role": "user", "content": prompt}], temperature=0.7, max_tokens=300),
            timeout=_SUGGESTIONS_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.info("Prep suggestions skipped sid=%s: %s: %s", session_id, type(exc).__name__, exc)
        return PrepSuggestionsResponse()
    raw = verdict.get("suggestions") if isinstance(verdict, dict) else None
    suggestions: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            text = " ".join(str(item or "").split())
            if not text:
                continue
            if len(text) > _SUGGESTION_MAX_CHARS:
                text = text[: _SUGGESTION_MAX_CHARS - 1] + "…"
            if text not in suggestions:
                suggestions.append(text)
            if len(suggestions) == 4:
                break
    return PrepSuggestionsResponse(suggestions=suggestions)


__all__ = [
    "get_prep_context",
    "get_prep_messages",
    "prep_message",
    "prep_message_stream",
    "suggest_prep_followups",
]
