"""Interview-preparation Agent (function-calling think-then-act loop).

``PrepAgent`` is per-request state (history, working memory, turn scratchpad)
plus the think-then-act tool loop. Turn mechanics live in sibling modules so
this file stays at orchestration level:

- per-turn toolset policy (freeze/expand, memory-write budget): :mod:`turn_tools`;
- working-context assembly and mid-turn compaction: :mod:`round_compaction`;
- chat orchestration (single round / event-stream final persistence): :mod:`chat`;
- domain tools: :mod:`tools` package (assembled by :mod:`tools.registry`);
  ask_user is in :mod:`ask_user`, streaming helpers in :mod:`streaming`,
  and tool execution in :mod:`tool_exec`.

Underscore helpers kept here (``_tool_definitions``, ``_build_context``,
``_compact_current_round``, …) are thin delegates preserving the historical
call surface pinned by routes and tests; the logic lives in the modules above.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.orm import Session

from realmock.domains.prep.models import PrepSession
from realmock.domains.prep.models import commit_session, utcnow
from realmock.platform.capabilities.ai.agent import WorkingMemory, run_agent_loop
from realmock.platform.capabilities.ai.context.blobs import compress_text_blob
from realmock.platform.capabilities.ai.context.options import CompactionOptions
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.capabilities.knowledge.search.web import SearchHit
from realmock.platform.core.agent_error_log import log_agent_error
from realmock.platform.core.errors import ApiBusinessError

from .ask_user import fallback_reply as _fallback_reply
from .chat import run_chat, run_chat_stream
from .context import PREP_SYSTEM, build_system_messages, normalize_ui_locale
from .round_compaction import (
    FALLBACK_CONTEXT_TOKENS,
    build_turn_context,
    compact_current_round,
    prefix_fingerprint,
)
from .streaming import event_loopbacks
from .tool_exec import build_execute_callback
from .turn_state import TurnState
from .tools import execute_prep_tool
from .turn_tools import (
    MAX_MEMORY_WRITES_PER_TURN,
    PREP_TOOL_DEFINITIONS,
    expand_turn_tools,
    freeze_turn_tools,
)

logger = logging.getLogger(__name__)

# Per-turn tool budget: 12 rounds x 3 tools (36 calls max). Chat turns are
# interactive, so rounds stay well below the resume-review budget (18x4);
# 12 rounds leave headroom for GitHub deep-dives (readme -> file -> commits)
# while the loop's last-round wrap-up hint still forces a timely close.
# Width stays at 3: wider parallel batches invite junk calls in chat context.
_MAX_TOOL_ROUNDS = 12
_MAX_TOOLS_PER_ROUND = 3
# Whole-turn budget: bounds worker + DB-session hold time. Worst case without
# it is 12 rounds x (an LLM call + up to 3x18s tools + compression) — tens of
# minutes. On timeout the tool loop aborts and the caller falls back to a
# closing answer.
_TURN_TIMEOUT_SECONDS = 600.0
# Tool-observation compression budget. The platform default (120s) targets batch
# jobs; interactive chat converges to 30s so one slow blob cannot stall a turn.
_COMPRESSION_TIMEOUT_SECONDS = 30.0

__all__ = ["PREP_TOOL_DEFINITIONS", "PrepAgent"]


class PrepAgent:
    """Interview-preparation coaching agent: per-session state, persistence, and tool-round control flow.

    Rebuilt per request around one ``PrepSession`` row: loads message history,
    derives working memory plus the session-objective anchor, and exposes
    :meth:`chat` / :meth:`chat_stream` turn entry points (orchestrated by
    :mod:`chat`). Chat turns mutate :attr:`messages` in place and persist via
    :meth:`_save`.
    """

    def __init__(self, session: PrepSession, llm: LLMClient):
        self.session = session
        self.llm = llm
        # Context window for model entry declarations; falls back to old value when unknown
        self.context_window = getattr(llm, "context_window", 0) or FALLBACK_CONTEXT_TOKENS
        # Visible waiting-line locale (set on first turn; product default zh-CN).
        self.reply_locale = "zh-CN"
        self._load_messages()
        self.memory = WorkingMemory.load_from_messages(self.messages)
        # Mechanical prompt-size estimate of the latest turn's model input,
        # refreshed by chat.finalize (0 until the first turn finalizes).
        self.last_prompt_estimate: int = 0
        # Per-turn mutable state (reset at every turn start in run_chat/_stream).
        self._turn_state = TurnState()
        # Observability for the stream envelope (set per turn, read by routes).
        self.last_turn_id: str = ""
        self.last_prefix_fingerprint: str = ""
        self.last_message_count: int = 0
        # Session objective anchor: keeps summaries role-anchored when the
        # user gave no explicit compression directive for the run.
        role = (getattr(session, "target_role", None) or "").strip()
        company = (getattr(session, "target_company", None) or "").strip()
        self._objective_line = (
            f"Session objective: interview prep for {role}"
            + (f" at {company}" if company else "")
            + ". Keep role-relevant conclusions prominent."
            if role
            else ""
        )

    def _load_messages(self) -> None:
        try:
            loaded = json.loads(self.session.messages or "[]")
        except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
            logger.warning(
                "Prep history corrupt, resetting to empty sid=%s",
                getattr(self.session, "id", ""),
            )
            self.messages: list[dict[str, Any]] = []
            return
        if not isinstance(loaded, list):
            logger.warning(
                "Prep history not a list, resetting to empty sid=%s",
                getattr(self.session, "id", ""),
            )
            self.messages = []
            return
        self.messages = loaded

    def _save(self, db: Session) -> None:
        self.session.messages = json.dumps(self.messages, ensure_ascii=False)
        # Conversation list sorted by most recently active
        self.session.updated_at = utcnow()
        commit_session(db)

    async def _ensure_system(self, db: Session, ui_locale: str | None = None) -> None:
        # The agent is rebuilt per request: refresh the visible-copy locale every
        # turn, not just on the first one (restored sessions skip system seeding).
        normalized = normalize_ui_locale(ui_locale)
        if normalized:
            self.reply_locale = normalized
        if self.messages:
            return
        # Prefix-stable seed: one system message per block, stable-first, so
        # prompt-cache prefixes survive volatile tail-block churn. Existing
        # sessions keep their legacy single-string seed untouched. The seed
        # builders touch synchronous SQLite, so they run off the event loop.
        # Degraded seed: resume/profile/company lookups must never fail the
        # turn — fall back to bare instructions (same never-raise policy as
        # the memory-index block).
        try:
            self.messages = await asyncio.to_thread(
                build_system_messages,
                db, resume_id=self.session.resume_id,
                target_company=self.session.target_company or "",
                linked_session_id=getattr(self.session, "linked_session_id", None),
            )
        except Exception as exc:
            logger.warning(
                "Prep system seed degraded sid=%s: %s",
                getattr(self.session, "id", ""), exc,
            )
            log_agent_error(
                domain="prep", session=str(getattr(self.session, "id", "") or ""),
                kind="seed_degraded", message=str(exc)[:200],
            )
            self.messages = [{"role": "system", "content": PREP_SYSTEM}]

    def pending_reply_text(self) -> str:
        """Deferred-turn reply text in the turn's reply language (shown while awaiting user input)."""
        return _fallback_reply(self.reply_locale)

    def waiting_line(self) -> str:
        """Deprecated alias for :meth:`pending_reply_text`."""
        return self.pending_reply_text()

    async def _build_context(
        self,
        threshold: float | None = None,
        force: bool = False,
        options: CompactionOptions | None = None,
        keep_from: int | None = None,
        provenance: dict[str, Any] | None = None,
        report: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Turn working context (delegates to :mod:`round_compaction`).

        Keeps the historical call surface used by chat orchestration and the
        history route; refreshes the prefix fingerprint as before.
        """
        working = await build_turn_context(
            messages=self.messages, context_window=self.context_window,
            memory=self.memory, llm=self.llm,
            reply_locale=self.reply_locale, threshold=threshold, force=force,
            options=options, keep_from=keep_from, provenance=provenance, report=report,
            default_focus=self._objective_line or None,
        )
        self.last_prefix_fingerprint = prefix_fingerprint(working, self._tool_definitions())
        return working

    def _tool_definitions(self, user_text: str = "") -> list[dict[str, Any]]:
        """Frozen turn toolset (delegates to :mod:`turn_tools`)."""
        return freeze_turn_tools(
            resume_id=getattr(self.session, "resume_id", None),
            user_text=user_text,
            turn_state=self._turn_state,
        )

    def _expand_turn_tools(self, selected: list[str]) -> list[str]:
        """Append on-demand schemas to the live turn toolset (see :mod:`turn_tools`)."""
        return expand_turn_tools(turn_state=self._turn_state, selected=selected)

    async def _compact_current_round(
        self, args: dict[str, Any], db: Session
    ) -> tuple[str, list[SearchHit]]:
        """Mid-turn compaction entry (body in :mod:`round_compaction`).

        Adopts and persists the compacted messages when the outcome carries
        any; ``compact_context`` bypasses the tool registry precisely because
        it rewrites agent history here, which plain handlers cannot reach.
        """
        outcome = await compact_current_round(
            messages=self.messages, context_window=self.context_window,
            memory=self.memory, llm=self.llm, reply_locale=self.reply_locale,
            turn_state=self._turn_state, objective_line=self._objective_line,
            resume_id=getattr(self.session, "resume_id", None), args=args,
        )
        if outcome.messages is not None:
            self.messages = outcome.messages
            self._save(db)
        if outcome.prefix_fingerprint is not None:
            self.last_prefix_fingerprint = outcome.prefix_fingerprint
        return outcome.text, outcome.hits

    async def _run_named_tool(
        self, name: str, args: dict[str, Any], db: Session
    ) -> tuple[str, list[SearchHit]]:
        """Execute domain tools (registry dispatch); return ``(observation_text, search_hits)``.

        ``compact_context`` bypasses the registry: it rewrites agent history
        and needs the agent (plus db for immediate persist), which handlers
        never receive. ``search_tools`` runs through the registry for its
        observation, then expands the live turn toolset here (same reason:
        only the agent owns the loop's declaration list).
        """
        if name == "compact_context":
            return await self._compact_current_round(args, db)
        if name == "memory_write":
            if self._turn_state.memory_writes >= MAX_MEMORY_WRITES_PER_TURN:
                return (
                    f"memory_write budget exhausted this turn (max {MAX_MEMORY_WRITES_PER_TURN}); "
                    "continue coaching without more writes.",
                    [],
                )
            self._turn_state.memory_writes += 1
        if name == "search_tools":
            text, hits = await execute_prep_tool(
                name, args, self.memory, resume_id=self.session.resume_id
            )
            if self._turn_state.expanded:
                return (
                    text + "\nToolset already expanded this turn; no further schemas loaded.",
                    hits,
                )
            self._turn_state.expanded = True
            selected: list[str] = []
            try:
                payload = json.loads(text) if isinstance(text, str) else {}
                raw = payload.get("loaded", []) if isinstance(payload, dict) else []
                selected = [str(n) for n in raw if isinstance(n, str)]
            except Exception:
                selected = []
            added = self._expand_turn_tools(selected)
            if added:
                return (
                    text + f"\nLoaded into this turn: {', '.join(added)} — callable next round.",
                    hits,
                )
            return text, hits
        return await execute_prep_tool(
            name, args, self.memory, resume_id=self.session.resume_id
        )

    def _build_execute(
        self,
        db: Session,
        search_groups: list[dict[str, Any]],
        events: asyncio.Queue | None,
        asked_user: dict[str, bool] | None,
    ):
        """Tool execution callback: ask_user dispatch, same-args dedup, circuit breaker, and timeout/retrieval-failure handling (see :mod:`tool_exec`)."""
        return build_execute_callback(
            run_named_tool=self._run_named_tool, memory=self.memory, db=db,
            search_groups=search_groups, events=events, asked_user=asked_user,
            error_context={"domain": "prep", "session": str(getattr(self.session, "id", "") or "")},
        )

    async def _run_tool_rounds(
        self,
        working: list[dict[str, Any]],
        db: Session,
        *,
        events: asyncio.Queue | None = None,
        asked_user: dict[str, bool] | None = None,
        content_state: dict[str, Any] | None = None,
    ) -> tuple[
        list[dict[str, Any]],
        str | None,
        list[dict[str, Any]],
        list[dict[str, Any]],
        str,
    ]:
        """Think-then-act tool loop over the frozen turn toolset.

        Args:
            working: Model input context for round one (loop appends in place).
            db: Sessions database session handed to tool handlers.
            events: Optional event queue for live thinking/tool/content callbacks.
            asked_user: Optional one-dialog gate flag shared with the executor.
            content_state: Optional caller-owned speculative-streaming state
                (streaming path only); the caller flushes the sanitizer's
                held-back tail afterwards.

        Returns:
            ``(messages, early_content, search_groups, tool_steps, thinking)``.
        """
        search_groups: list[dict[str, Any]] = []
        tool_steps: list[dict[str, Any]] = []
        on_thinking, on_tool, on_content = event_loopbacks(
            events, on_tool_step=tool_steps.append, content_state=content_state,
        )
        # Turn-relevant static subset, resolved once per turn from the latest
        # user input; the SAME list object feeds every round so mid-turn
        # search_tools expansion (append-only) is visible next round.
        user_text = ""
        for m in reversed(working or []):
            if isinstance(m, dict) and m.get("role") == "user":
                content = m.get("content")
                user_text = content if isinstance(content, str) else ""
                break
        turn_tools = self._tool_definitions(user_text)

        async def compact_observation(text: str) -> str:
            try:
                return await asyncio.wait_for(
                    compress_text_blob(self.llm, text, purpose="prep tool result"),
                    timeout=_COMPRESSION_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Prep observation compression timed out (%.0fs); falling back to truncation",
                    _COMPRESSION_TIMEOUT_SECONDS,
                )
                # compress_text_blob already marks failures explicitly; truncate
                # here with the same explicit marker instead of a silent cut.
                clipped = str(text or "")
                return clipped if len(clipped) <= 4000 else (
                    clipped[:2000]
                    + f"\n…[COMPRESSION_TIMEOUT: middle omitted; original {len(clipped)} chars]…\n"
                    + clipped[-2000:]
                )

        error_scope = {"domain": "prep", "session": str(getattr(self.session, "id", "") or "")}
        try:
            loop = await asyncio.wait_for(
                run_agent_loop(
                    self.llm,
                    working,
                    tools=turn_tools,
                    execute=self._build_execute(db, search_groups, events, asked_user),
                    max_rounds=_MAX_TOOL_ROUNDS,
                    max_tools_per_round=_MAX_TOOLS_PER_ROUND,
                    temperature=0.7,
                    on_tool=on_tool,
                    on_thinking=on_thinking,
                    on_content=on_content,
                    drift_retry=True,
                    compact_observation=compact_observation,
                    error_context=error_scope,
                ),
                timeout=_TURN_TIMEOUT_SECONDS,
            )
        except ApiBusinessError:
            # Business failures propagate to routes for catalog HTTP errors;
            # they must never degrade into an empty silent turn.
            raise
        except asyncio.TimeoutError:
            logger.warning(
                "Prep tool rounds exceeded %.0fs turn budget; falling back to closing answer",
                _TURN_TIMEOUT_SECONDS,
            )
            log_agent_error(
                domain=error_scope["domain"], session=error_scope["session"],
                kind="turn_timeout",
                message=f"Tool rounds exceeded {_TURN_TIMEOUT_SECONDS:.0f}s",
            )
            return working, None, search_groups, tool_steps, ""
        except Exception as e:
            logger.warning("Prep tool round failed: %s", e)
            return working, None, search_groups, tool_steps, ""
        return (
            loop.messages,
            loop.final_content,
            search_groups,
            tool_steps,
            loop.thinking,
        )

    async def chat(
        self, user_text: str, db: Session, *,
        drop_last_assistant: bool = False, ui_locale: str | None = None,
        context_session_ids: list[int] | None = None,
        compact_threshold: float | None = None,
        compact_options: CompactionOptions | None = None,
    ) -> str:
        """Synchronous single-round reply (arrangement and storage in :mod:`chat`).

        Args:
            user_text: Latest user message content.
            db: Sessions database session (turn persists through it).
            drop_last_assistant: Regenerate support — drop the trailing reply first.
            ui_locale: UI locale hint for the reply language (zh-CN/en).
            context_session_ids: Per-turn referenced sessions (transient injection).
            compact_threshold: Auto-compact trigger fraction (None = agent default).
            compact_options: Compaction intensity/directive/retain policy.

        Returns:
            The sanitized final reply text.
        """
        return await run_chat(
            self, user_text, db,
            drop_last_assistant=drop_last_assistant, ui_locale=ui_locale,
            context_session_ids=context_session_ids,
            compact_threshold=compact_threshold,
            compact_options=compact_options,
        )

    async def chat_stream(
        self, user_text: str, db: Session, *,
        drop_last_assistant: bool = False, ui_locale: str | None = None,
        context_session_ids: list[int] | None = None,
        compact_threshold: float | None = None,
        compact_options: CompactionOptions | None = None,
    ) -> AsyncIterator[str | dict[str, Any]]:
        """Think-then-act tool loop (events pushed immediately) → then stream the final answer (orchestration in :mod:`chat`).

        Args:
            user_text: Latest user message content.
            db: Sessions database session (turn persists through it).
            drop_last_assistant: Regenerate support — drop the trailing reply first.
            ui_locale: UI locale hint for the reply language (zh-CN/en).
            context_session_ids: Per-turn referenced sessions (transient injection).
            compact_threshold: Auto-compact trigger fraction (None = agent default).
            compact_options: Compaction intensity/directive/retain policy.

        Yields ``str`` (response-body token) or ``dict`` (``status`` / ``thinking`` /
        ``tool_step`` / ``search_results`` / ``ask_user`` / ``usage`` / ``compaction`` events).
        """
        async for item in run_chat_stream(
            self, user_text, db,
            drop_last_assistant=drop_last_assistant, ui_locale=ui_locale,
            context_session_ids=context_session_ids,
            compact_threshold=compact_threshold,
            compact_options=compact_options,
        ):
            yield item
