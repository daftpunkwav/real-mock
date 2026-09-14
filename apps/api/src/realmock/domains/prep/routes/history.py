"""Prep history surgery: compaction, summary edits, forks, and truncation.

Split from ``chat.py`` (turn messaging) so each route module owns one duty:
``chat.py`` runs turns and reads history; this module rewrites history.
Shared primitives (session loading, tool-tail pruning) live here; ``chat.py``
imports the loader from this module.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from realmock.domains.prep.agents.agent import PrepAgent
from realmock.domains.prep.models import PrepSession
from realmock.domains.prep.models import commit_session, utcnow
from realmock.domains.prep.schemas import (
    PrepCompactRequest,
    PrepCompactResponse,
    PrepForkRequest,
    PrepSummaryUpdateRequest,
    PrepTruncateRequest,
)
from realmock.platform.capabilities.ai.context.compress import (
    COMPACTION_DIGEST_MARKER,
    COMPACTION_SUMMARY_MARKER,
)
from realmock.platform.capabilities.ai.context.estimation import estimate_messages_tokens
from realmock.platform.capabilities.ai.context.options import CompactionOptions
from realmock.platform.capabilities.ai.context.summarize import (
    format_provenance,
    parse_provenance,
    strip_provenance,
)
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.core.constants import SessionStatus
from realmock.platform.core.errors import raise_error
from realmock.platform.core.session_auth import (
    assert_session_token,
    cookie_should_be_secure,
    extract_prep_token,
    new_access_token,
    set_session_cookie,
)
from realmock.platform.core.session_auth.csrf import assert_csrf_if_cookie_only
from realmock.platform.database import get_api_db, get_sessions_db

logger = logging.getLogger(__name__)

_PREP_FORBIDDEN = "Don't have access to this coaching session"


def _require_existing_writable_session(session_id: int, db: Session) -> PrepSession:
    """Owner-level writable session (compact/summary/truncate): no token so orphans stay manageable."""
    session = db.query(PrepSession).filter(PrepSession.id == session_id).first()
    if not session:
        raise_error("A3001")
    if getattr(session, "status", None) == SessionStatus.COMPLETED.value:
        raise_error("A3002")
    return session


def _load_session_messages(session: PrepSession) -> list[dict]:
    """Load and validate persisted history (corrupt stores serve empty, with a warning)."""
    try:
        messages = json.loads(session.messages or "[]")
    except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
        logger.warning(
            "Prep history unreadable, serving empty sid=%s len=%s",
            getattr(session, "id", ""), len(session.messages or ""),
        )
        return []
    if not isinstance(messages, list):
        logger.warning(
            "Prep history not a list, serving empty sid=%s", getattr(session, "id", ""),
        )
        return []
    return messages


def _call_ids(message: dict) -> list[str]:
    """Tool-call ids declared by one assistant message (tolerates corrupt shapes)."""
    calls = message.get("tool_calls")
    if not isinstance(calls, list):
        return []
    return [str(tc.get("id") or "") for tc in calls if isinstance(tc, dict)]


def _prune_dangling_tool_tail(messages: list[dict]) -> list[dict]:
    """Drop tail tool-call groups broken by a prefix cut (truncate/fork).

    A cut between an assistant ``tool_calls`` message and its results leaves an
    unpaired tail that the provider rejects on the next request. Walks from the
    end: orphan tool results, incomplete result runs, and trailing tool-calling
    assistants are removed until the tail is protocol-clean. Mid-history pairs
    cannot be broken by a suffix cut and are left untouched.
    """
    out = [m for m in messages if isinstance(m, dict)]
    while True:
        if not out:
            return out
        last = out[-1]
        role = last.get("role")
        if role == "assistant" and _call_ids(last):
            # An assistant with tool_calls must be followed by a full result run.
            out.pop()
            continue
        if role == "tool":
            call_id = str(last.get("tool_call_id") or "")
            owner = -1
            for i in range(len(out) - 1, -1, -1):
                candidate = out[i]
                if candidate.get("role") != "assistant":
                    continue
                if call_id in _call_ids(candidate):
                    owner = i
                break
            if owner >= 0:
                ids_after, reached_end = _result_ids_after(out, owner)
                if reached_end and ids_after == sorted(_call_ids(out[owner])):
                    return out
            out.pop()
            continue
        return out


def _result_ids_after(messages: list[dict], owner: int) -> tuple[list[str], bool]:
    """Sorted ids of the consecutive tool-result run after ``owner``.

    The second item says whether the run extends to the end of the list —
    an interrupted run means a non-tool message (or more corruption) follows,
    so the tail is not a clean pair group.
    """
    ids: list[str] = []
    j = owner + 1
    while j < len(messages) and messages[j].get("role") == "tool":
        ids.append(str(messages[j].get("tool_call_id") or ""))
        j += 1
    return sorted(ids), j == len(messages)


def _has_summary_block(messages: list[dict]) -> set[str]:
    """Summarized-content fingerprints for /compact change detection."""
    marks: set[str] = set()
    for m in messages:
        if not isinstance(m, dict) or m.get("role") != "system":
            continue
        content = str(m.get("content") or "")
        if content.startswith((COMPACTION_SUMMARY_MARKER, COMPACTION_DIGEST_MARKER)):
            marks.add(content[:200])
    return marks


def _find_summary_block(messages: list[dict]) -> int:
    """Backend index of the latest LLM summary block (-1 when absent)."""
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if (
            isinstance(m, dict)
            and m.get("role") == "system"
            and str(m.get("content") or "").startswith(COMPACTION_SUMMARY_MARKER)
        ):
            return i
    return -1


def _copy_session_row(
    db: Session, session: PrepSession, kept: list[dict], status: str
) -> PrepSession:
    """Fork helper: duplicate history into a new session row (shared by fork/backup)."""
    forked = PrepSession(
        resume_id=session.resume_id,
        target_role=session.target_role or "",
        target_company=session.target_company or "",
        messages=json.dumps(kept, ensure_ascii=False),
        status=status,
        access_token=new_access_token(),
        linked_session_id=session.linked_session_id,
    )
    db.add(forked)
    commit_session(db)
    db.refresh(forked)
    return forked


async def compact_prep_session(
    session_id: int,
    request: Request,
    db: Session = Depends(get_sessions_db),
    api_db: Session = Depends(get_api_db),
    body: PrepCompactRequest | None = None,
):
    """Run turn-start compaction now (the ``/compact`` slash command).

    Manual compaction is user-decided: it always attempts an LLM summary
    (never a silent truncation), folding to the latest turn regardless of
    the retain window — a lone remaining exchange folds whole, so any
    history produces a summary. The summary keeps session objectives,
    confirmed decisions, user weaknesses/requirements, findings, and
    to-dos, steered by the optional intensity/directive/retain parameters
    (``/compact`` slash args or the prep settings defaults). The LLM
    failure propagates as an error instead of falling back to truncation.
    When the summarizer fails, the just-created backup is deleted again so no
    orphan archive survives the failed run.
    Only a truly empty history reports ``summarized=False``.
    A rolling backup fork (archived, at most one per session) preserves the
    pre-compaction originals; the summary trailer links it for fork-from-point
    restores. Regeneration reuses this endpoint with ``backup=False``.
    Owner-level: CSRF-protected, no capability token (orphans must stay compactable).
    """
    assert_csrf_if_cookie_only(request, used_header=False)
    session = _require_existing_writable_session(session_id, db)
    params = body or PrepCompactRequest()
    llm = LLMClient.from_db(api_db)
    agent = PrepAgent(session, llm)
    if params.expected_message_count is not None and params.expected_message_count != len(agent.messages):
        raise_error("A3003")
    options = CompactionOptions.resolve(
        intensity=params.intensity, directive=params.directive, retain=params.retain,
    )
    before = estimate_messages_tokens(agent.messages)
    had = _has_summary_block(agent.messages)
    fork_point = len(agent.messages)

    backup_session_id: int | None = None
    if params.backup and any(
        isinstance(m, dict) and m.get("role") in ("user", "assistant") for m in agent.messages
    ):
        # Create the new backup first, then retire the previous rolling backup:
        # SQLite may reuse the freed row id, so deleting first would let the
        # new backup inherit the old id and the "replaced" check could never hold.
        backup = _copy_session_row(db, session, list(agent.messages), SessionStatus.ARCHIVED.value)
        backup_session_id = backup.id
        previous = parse_provenance(_current_summary_text(agent.messages)).get("backup_session")
        if isinstance(previous, int) and previous not in (session_id, backup_session_id):
            stale = db.query(PrepSession).filter(PrepSession.id == previous).first()
            if stale is not None:
                db.delete(stale)
                commit_session(db)

    report: dict[str, Any] = {}
    try:
        working = await agent._build_context(
            force=True, options=options,
            provenance={"backup_session_id": backup_session_id, "fork_point": fork_point},
            report=report,
        )
    except Exception:
        # The backup above is already committed: remove it so a failed LLM run
        # does not leave an orphan archive behind. The original error propagates.
        if backup_session_id is not None:
            stale_backup = db.query(PrepSession).filter(PrepSession.id == backup_session_id).first()
            if stale_backup is not None:
                db.delete(stale_backup)
                commit_session(db)
        raise
    summarized = bool(_has_summary_block(working) - had)
    agent.messages = working
    await asyncio.to_thread(agent._save, db)
    after = estimate_messages_tokens(agent.messages)
    summary_text, summary_version = _current_summary(agent.messages)
    if summarized:
        reason = "summarized"
    elif after < before:
        reason = "tool_pairs_only"
    else:
        reason = "nothing_to_fold"
    kept_from = report.get("kept_from")
    return PrepCompactResponse(
        message_count=len(agent.messages),
        summarized=summarized,
        estimate_before=before,
        estimate_after=after,
        reason=reason,
        summary_text=summary_text,
        summary_version=summary_version,
        fork_point=fork_point,
        backup_session_id=backup_session_id,
        kept_from=int(kept_from) if isinstance(kept_from, int) else None,
        compaction_prompt_tokens=int(report.get("prompt_tokens", 0)),
        compaction_completion_tokens=int(report.get("completion_tokens", 0)),
        compaction_latency_ms=round(float(report.get("latency_ms", 0.0)), 1),
    )


def _current_summary(messages: list[dict]) -> tuple[str, int]:
    """Latest summary text (trailer stripped) and provenance version (0/empty when absent)."""
    idx = _find_summary_block(messages)
    if idx < 0:
        return "", 0
    content = str(messages[idx].get("content") or "")
    version = parse_provenance(content).get("v", 0)
    return strip_provenance(content[len(COMPACTION_SUMMARY_MARKER):].strip()), int(version or 0)


def _current_summary_text(messages: list[dict]) -> str:
    """Raw latest summary block content (empty when absent)."""
    idx = _find_summary_block(messages)
    if idx < 0:
        return ""
    return str(messages[idx].get("content") or "")


async def update_prep_summary(
    session_id: int,
    body: PrepSummaryUpdateRequest,
    request: Request,
    db: Session = Depends(get_sessions_db),
):
    """Replace the current compaction summary text (user-edited correction).

    The provenance trailer is managed server-side: version increments, the
    backup/fork-point linkage carries over. 404 (A3004) when no summary exists
    yet; 409 (A3003) on a concurrent history change.
    Owner-level: CSRF-protected, no capability token.

    Args:
        session_id: Target session id.
        body: Edited summary text plus optional concurrency guard.
        request: Active request (used for CSRF validation).
        db: Sessions database session (injected).

    Returns:
        Compaction-shaped response describing the edited summary.

    Raises:
        ApiBusinessError: A3001 (missing session), A3002 (completed),
            A3003 (history changed), A3004 (no summary yet).
    """
    assert_csrf_if_cookie_only(request, used_header=False)
    session = _require_existing_writable_session(session_id, db)
    agent = PrepAgent(session, llm=None)  # type: ignore[arg-type]
    if body.expected_message_count is not None and body.expected_message_count != len(agent.messages):
        raise_error("A3003")
    idx = _find_summary_block(agent.messages)
    if idx < 0:
        raise_error("A3004")
    old = parse_provenance(str(agent.messages[idx].get("content") or ""))

    def _opt_int(value: Any) -> int | None:
        return value if isinstance(value, int) else None

    trailer = format_provenance(
        version=int(old.get("v", 0) or 0) + 1,
        backup_session_id=_opt_int(old.get("backup_session")),
        fork_point=_opt_int(old.get("fork_point")),
        focus=str(old.get("focus") or ""),
        before=_opt_int(old.get("before")),
        after=_opt_int(old.get("after")),
        base=_opt_int(old.get("base")),
    )
    agent.messages[idx] = {
        "role": "system",
        "content": f"{COMPACTION_SUMMARY_MARKER} {body.text.strip()}\n{trailer}",
    }
    await asyncio.to_thread(agent._save, db)
    summary_text, summary_version = _current_summary(agent.messages)
    estimate = estimate_messages_tokens(agent.messages)
    return PrepCompactResponse(
        message_count=len(agent.messages),
        summarized=False,
        estimate_before=estimate,
        estimate_after=estimate,
        reason="edited",
        summary_text=summary_text,
        summary_version=summary_version,
        fork_point=old.get("fork_point") if isinstance(old.get("fork_point"), int) else None,
        backup_session_id=old.get("backup_session") if isinstance(old.get("backup_session"), int) else None,
    )


async def fork_prep_session(
    session_id: int,
    body: PrepForkRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_sessions_db),
    access: str | None = Depends(extract_prep_token),
):
    """Branch a new active session copying history through ``up_to`` (inclusive).

    ``up_to`` normalization: any negative keeps everything; positives clamp to
    the last message. The fork starts with zeroed usage counters (fresh branch
    accounting) but inherits resume/role/company/linked context.

    Args:
        session_id: Source session id (capability-token gated).
        body: Fork parameters (``up_to`` index plus optional concurrency guard).
        request: Active request (used for secure-cookie detection).
        response: Response used to seed the fork's capability cookie.
        db: Sessions database session (injected).
        access: Source session capability token (injected).

    Returns:
        Mapping with the fork id and copied message count.

    Raises:
        ApiBusinessError: A3001 (missing session), A0401 (token mismatch).
    """
    session = db.query(PrepSession).filter(PrepSession.id == session_id).first()
    if not session:
        raise_error("A3001")
    assert_session_token(session, access, detail=_PREP_FORBIDDEN)
    messages = _load_session_messages(session)
    if body.up_to < 0:
        kept = list(messages)
    else:
        kept = messages[: min(body.up_to + 1, len(messages))]
    kept = _prune_dangling_tool_tail(kept)
    forked = _copy_session_row(db, session, kept, SessionStatus.ACTIVE.value)
    set_session_cookie(
        response,
        scope="prep",
        session_id=forked.id,
        token=forked.access_token,
        secure=cookie_should_be_secure(request),
    )
    return {"id": forked.id, "message_count": len(kept)}


async def truncate_prep_messages(
    session_id: int,
    body: PrepTruncateRequest,
    request: Request,
    db: Session = Depends(get_sessions_db),
):
    """Retract a user message: drop backend history from ``from_index`` on.

    Owner-level: CSRF-protected, no capability token (orphans must stay clearable).

    Args:
        session_id: Target session id.
        body: Truncation parameters (``from_index`` plus optional concurrency guard).
        request: Active request (used for CSRF validation).
        db: Sessions database session (injected).

    Returns:
        Mapping with the remaining backend-truth message count.

    Raises:
        ApiBusinessError: A3001 (missing session), A3002 (completed), A3003 (history changed).
    """
    assert_csrf_if_cookie_only(request, used_header=False)
    session = _require_existing_writable_session(session_id, db)
    messages = _load_session_messages(session)
    if body.expected_message_count is not None and body.expected_message_count != len(messages):
        raise_error("A3003")
    cut = max(0, min(len(messages), body.from_index))
    kept = _prune_dangling_tool_tail(messages[:cut])
    session.messages = json.dumps(kept, ensure_ascii=False)
    session.updated_at = utcnow()
    commit_session(db)
    return {"message_count": len(kept)}


__all__ = [
    "compact_prep_session",
    "fork_prep_session",
    "truncate_prep_messages",
    "update_prep_summary",
]
