"""Persistent interview-history folding (InterviewSessionState companion).

The per-turn prompt path (:mod:`prompt_assembler`) already compacts
ephemerally via :func:`compact_with_summary`, but the folded result is
discarded: ``agent.messages`` and the ``session.messages`` DB column keep
growing for the whole interview (write amplification in ``save_state`` on
every turn, plus a repeated summarizer call once over budget).

This module persists the fold: after a turn completes, histories past half
the context window are folded into incremental session minutes and adopted
as the new ``agent.messages`` before ``save_state``. The next turn then
starts below budget, so the ephemeral path becomes a no-op instead of
re-summarizing every turn.

Recall paths (never folded away):
- ``ledger`` keeps every turn verbatim (question/answer/tool previews);
- ``agent_state`` keeps ``asked_questions`` / ``weak_points`` / turn scores;
- the plan (``session.plan``) is untouched — steps are not history.

Failure never raises: on any error the original messages are kept and the
turn proceeds (the ephemeral per-call compaction still bounds the LLM call).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from realmock.platform.capabilities.ai.agent import WorkingMemory
from realmock.platform.capabilities.ai.context.estimation import estimate_messages_tokens
from realmock.platform.capabilities.ai.context.summarize import compact_with_summary

if TYPE_CHECKING:
    from realmock.domains.interview.agents.session_state import InterviewSessionState

logger = logging.getLogger(__name__)

#: Persist the fold once history passes this fraction of the context window.
#: Higher than the ephemeral path's default (0.3): rewriting the record of
#: truth should lag one step behind the per-call safety net.
PERSIST_FOLD_RATIO = 0.5

#: Verbatim tail kept on fold (matches the prompt path's keep-recent window).
FOLD_KEEP_RECENT = 20

#: Focus directive for interview minutes (question-answer mapping first).
FOLD_FOCUS = (
    "Interview minutes: per-question candidate answers and demonstrated skill "
    "level, weaknesses with evidence, questions already asked (never repeat "
    "them), and agreed facts (company/role/compensation)."
)

#: Cap on the compactions audit log kept in agent_state (observability only).
MAX_COMPACTION_LOG = 20


async def maybe_fold_history(
    agent: "InterviewSessionState",
    *,
    llm: Any | None,
    context_window: int | None,
    keep_recent: int = FOLD_KEEP_RECENT,
) -> bool:
    """Fold old history into session minutes and adopt it when over budget.

    Returns True when ``agent.messages`` (and the working-memory patch) was
    replaced; False when nothing changed (unlimited window, below budget,
    cooldown, nothing worth folding, or any failure).
    """
    try:
        window = int(context_window or 0)
    except (TypeError, ValueError):
        window = 0
    if window <= 0:
        return False
    messages = getattr(agent, "messages", None)
    if not messages or len(messages) <= keep_recent + 1:
        return False
    try:
        if estimate_messages_tokens(messages) <= window * PERSIST_FOLD_RATIO:
            return False
    except Exception:
        logger.debug("history fold estimate failed; skip", exc_info=True)
        return False

    before_msgs = len(messages)
    try:
        before_tokens = estimate_messages_tokens(messages)
    except Exception:
        before_tokens = -1
    try:
        memory = WorkingMemory.from_state(agent.agent_state)
        folded = await compact_with_summary(
            list(messages),
            window,
            memory=memory,
            llm=llm,
            keep_recent=keep_recent,
            threshold=PERSIST_FOLD_RATIO,
            default_focus=FOLD_FOCUS,
        )
    except Exception:
        logger.warning("history fold failed; keep original messages", exc_info=True)
        return False
    if len(folded) >= before_msgs:
        return False
    try:
        after_tokens = estimate_messages_tokens(folded)
    except Exception:
        after_tokens = -1
    agent.messages = folded
    try:
        agent.agent_state.update(memory.to_state_patch())
        log = agent.agent_state.setdefault("compactions", [])
        log.append({
            "at": datetime.now(timezone.utc).isoformat(),
            "before_msgs": before_msgs,
            "after_msgs": len(folded),
            "before_tokens": before_tokens,
            "after_tokens": after_tokens,
        })
        del log[:-MAX_COMPACTION_LOG]
    except Exception:
        logger.debug("history fold audit log failed; fold still adopted", exc_info=True)
    logger.info(
        "history folded %d->%d msgs (%s->%s tokens)",
        before_msgs, len(folded), before_tokens, after_tokens,
    )
    return True


__all__ = ["FOLD_FOCUS", "FOLD_KEEP_RECENT", "PERSIST_FOLD_RATIO", "maybe_fold_history"]
