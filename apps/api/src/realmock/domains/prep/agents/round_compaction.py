"""Mid-turn context compaction for the prep agent.

Extracted from :mod:`agent`: the per-turn working-context assembly
(:func:`build_turn_context`), the agent-invoked ``compact_context`` tool body
(:func:`compact_current_round`), and the cache-prefix fingerprint helper.

Design notes (preserved from the original):
- Compaction occurs only at the start of each conversation turn (plus at most
  one agent-invoked mid-turn fold); the persistence path (``chat.finalize``)
  uses rule-based compaction and adds no latency while saving.
- These functions take explicit state — they never reach into ``PrepAgent``.
  The agent owns adoption: when :attr:`MidTurnCompaction.messages` is not
  ``None`` the caller must adopt the list and persist it. ``turn_state`` is
  mutated in place (it is the designated per-turn scratchpad, see
  :mod:`turn_state`).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

from realmock.platform.capabilities.ai.agent import WorkingMemory
from realmock.platform.capabilities.ai.context.estimation import estimate_messages_tokens
from realmock.platform.capabilities.ai.context.options import CompactionOptions
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.capabilities.ai.llm.defaults import DEFAULT_CONTEXT_WINDOW
from realmock.platform.capabilities.knowledge.search.web import SearchHit
from realmock.platform.core.security import redact_api_key

from .context import build_working_context
from .turn_state import TurnState
from .turn_tools import freeze_turn_tools

logger = logging.getLogger(__name__)

#: Fallback value when the model context window is unknown.
FALLBACK_CONTEXT_TOKENS = DEFAULT_CONTEXT_WINDOW

#: Absolute usage floor below which the agent-invoked compact tool refuses to
#: run (tiny sessions have nothing worth an extra summarizer call).
COMPACT_TOOL_MIN_RATIO = 0.3


@dataclass
class MidTurnCompaction:
    """Outcome of one agent-invoked mid-turn compaction."""

    #: Human-readable observation text for the tool loop.
    text: str
    #: Search hits produced (always empty for compaction; kept for dispatch uniformity).
    hits: list[SearchHit] = field(default_factory=list)
    #: Compacted message list for the caller to adopt + persist; ``None`` means
    #: no state change (guard refused before touching anything).
    messages: list[dict[str, Any]] | None = None
    #: Refreshed cache-prefix fingerprint for the caller to adopt; ``None``
    #: when nothing changed.
    prefix_fingerprint: str | None = None


def prefix_fingerprint(
    working: list[dict[str, Any]], tool_definitions: list[dict[str, Any]]
) -> str:
    """Stable-prefix fingerprint for cache-hit measurement (never raises).

    Covers the cacheable head only: leading system blocks plus sorted tool
    names. Volatile tails (history, refs, lang hint) are excluded by design,
    so equal fingerprints across turns mean the provider prefix cache can hit.
    """
    try:
        parts: list[str] = []
        for m in working or []:
            if not isinstance(m, dict) or m.get("role") != "system":
                break
            parts.append(str(m.get("content") or ""))
        names = sorted(
            str(t.get("function", {}).get("name") or "")
            for t in tool_definitions or []
            if isinstance(t, dict)
        )
        parts.extend(n for n in names if n)
        return hashlib.sha256("\n\x00".join(parts).encode("utf-8")).hexdigest()[:16]
    except Exception:
        return ""


async def build_turn_context(
    *,
    messages: list[dict[str, Any]],
    context_window: int,
    memory: WorkingMemory,
    llm: LLMClient,
    reply_locale: str,
    threshold: float | None = None,
    force: bool = False,
    options: CompactionOptions | None = None,
    keep_from: int | None = None,
    provenance: dict[str, Any] | None = None,
    report: dict[str, Any] | None = None,
    default_focus: str | None = None,
) -> list[dict[str, Any]]:
    """Context assembly for the model: LLM-generated summary compaction + working-memory injection.

    Compaction occurs only at the start of each conversation turn (and may trigger one LLM summary call).
    ``threshold`` carries the user's auto-compact setting (``None`` = agent-decided default);
    ``force`` (manual ``/compact``) always attempts an LLM summary.
    ``options`` carries intensity/directive/retain; ``keep_from`` pins the
    verbatim cutoff for mid-turn agent-invoked compaction; ``provenance``
    stamps the new summary trailer; ``report`` collects compaction cost
    without raising.
    """
    return await build_working_context(
        messages, context_window, memory=memory, llm=llm,
        reply_locale=reply_locale, threshold=threshold, force=force,
        options=options, keep_from=keep_from, provenance=provenance, report=report,
        default_focus=default_focus,
    )


async def compact_current_round(
    *,
    messages: list[dict[str, Any]],
    context_window: int,
    memory: WorkingMemory,
    llm: LLMClient,
    reply_locale: str,
    turn_state: TurnState,
    objective_line: str,
    resume_id: int | None,
    args: dict[str, Any],
) -> MidTurnCompaction:
    """Agent-invoked mid-turn compaction (the ``compact_context`` tool body).

    Folds everything before the current user message into an LLM summary.
    The in-flight tool round continues on its working copy and chat.finalize
    merges the new tail back on top (so tool-call pairing never splits).
    Guarded: once per turn, and refused below an absolute usage floor.
    Per-call ``focus``/``intensity`` args override the turn policy for this
    run only (validated, never raising).

    Returns a :class:`MidTurnCompaction`; the caller adopts
    :attr:`~MidTurnCompaction.messages` (persist it) and
    :attr:`~MidTurnCompaction.prefix_fingerprint` when set.
    """
    call_args = args if isinstance(args, dict) else {}
    if turn_state.compact_used:
        return MidTurnCompaction(
            text="Compaction already ran this turn; continuing with the compacted context."
        )
    window = context_window or FALLBACK_CONTEXT_TOKENS
    usage = estimate_messages_tokens(messages)
    if window > 0 and usage <= window * COMPACT_TOOL_MIN_RATIO:
        return MidTurnCompaction(
            text=(
                f"Compaction not needed yet (usage ~{usage} tokens is below the "
                "minimum for a summarizer call); continuing with full history. "
                "Do not call compact_context again this turn."
            )
        )
    rest = [m for m in messages if isinstance(m, dict) and m.get("role") != "system"]
    last_user = max(
        (i for i, m in enumerate(rest) if m.get("role") == "user"),
        default=-1,
    )
    if last_user < 0:
        return MidTurnCompaction(text="No user turn to protect yet; compaction refused.")
    before = usage
    report: dict[str, Any] = {}
    policy = CompactionOptions.resolve(
        intensity=call_args.get("intensity"),
        directive=call_args.get("focus"),
        default=turn_state.policy,
    )
    try:
        compacted = await build_turn_context(
            messages=messages, context_window=context_window, memory=memory,
            llm=llm, reply_locale=reply_locale,
            force=True, options=policy, keep_from=last_user, report=report,
            default_focus=objective_line or None,
        )
    except Exception as e:
        safe_detail = redact_api_key(str(e))[:200]
        logger.warning("Agent-invoked compaction failed: %s", safe_detail)
        return MidTurnCompaction(
            text=f"Compaction failed ({safe_detail}); continuing with full history."
        )
    turn_state.compact_used = True
    turn_state.mid_turn_base = compacted
    after = estimate_messages_tokens(compacted)
    turn_state.mid_turn_report = {
        "before": before,
        "after": after,
        "summarized": True,
        "prompt_tokens": int(report.get("prompt_tokens", 0)),
        "completion_tokens": int(report.get("completion_tokens", 0)),
        "latency_ms": round(float(report.get("latency_ms", 0.0)), 1),
    }
    # Same refresh the agent always ran after a mid-turn fold: re-freeze the
    # turn toolset (empty user text, matching the original call) so the
    # fingerprint covers the declarations actually in force.
    fingerprint = prefix_fingerprint(
        compacted,
        freeze_turn_tools(resume_id=resume_id, user_text="", turn_state=turn_state),
    )
    return MidTurnCompaction(
        text=(
            f"Context compacted by summarizer ({policy.intensity}"
            + (f", focus: {policy.directive}" if policy.directive else "")
            + f"): ~{before} → ~{after} tokens. "
            "Older turns are now a sectioned summary; the current turn continues unchanged."
        ),
        messages=compacted,
        prefix_fingerprint=fingerprint,
    )


__all__ = [
    "COMPACT_TOOL_MIN_RATIO",
    "FALLBACK_CONTEXT_TOKENS",
    "MidTurnCompaction",
    "build_turn_context",
    "compact_current_round",
    "prefix_fingerprint",
]
