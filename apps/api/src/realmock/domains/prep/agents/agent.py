"""Interview-preparation Agent (function-calling think-then-act loop).

- The tool loop is driven by :func:`run_agent_loop`; the streaming interface immediately pushes tool_step / thinking /
  body-text tokens / search_results / ask_user / usage events to the frontend through ``asyncio.Queue``;
- For chat orchestration (synchronous single round / event-stream final persistence), see :mod:`chat`;
- For domain tools, see the :mod:`tools` package (assembled by :mod:`tools.registry`); ask_user is in :mod:`ask_user`, context in
  :mod:`context`, streaming helpers in :mod:`streaming`, and tool execution in :mod:`tool_exec`.
  This module retains only class state, message persistence, and tool-round control flow.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.orm import Session

from realmock.domains.prep.models import PrepSession
from realmock.domains.prep.models import commit_session, utcnow
from realmock.platform.capabilities.ai.agent import WorkingMemory, run_agent_loop
from realmock.platform.capabilities.ai.context.blobs import compress_text_blob
from realmock.platform.capabilities.ai.context.estimation import estimate_messages_tokens
from realmock.platform.capabilities.ai.context.options import CompactionOptions
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.capabilities.ai.llm.defaults import DEFAULT_CONTEXT_WINDOW
from realmock.platform.capabilities.knowledge.search.web import SearchHit
from realmock.platform.core.agent_error_log import log_agent_error
from realmock.platform.core.errors import ApiBusinessError
from realmock.platform.core.security import redact_api_key

from .ask_user import ASK_USER_TOOL
from .ask_user import fallback_reply as _fallback_reply
from .chat import run_chat, run_chat_stream
from .context import PREP_SYSTEM, build_system_messages, build_working_context, normalize_ui_locale
from .streaming import event_loopbacks
from .tool_exec import build_execute_callback
from .turn_state import TurnState
from .tools import execute_prep_tool
from .tools import COMPACT_TOOL_DEFINITION as _COMPACT_TOOL_DEFINITION
from .tools import PREP_TOOL_DEFINITIONS as _DOMAIN_TOOL_DEFS
from .tools import SECONDARY_DEFINITIONS as _SECONDARY_DEFINITIONS
from .tools import TOOL_REGISTRY as _TOOL_REGISTRY
from .tools import TOOL_TIER_SECONDARY as _TIER_SECONDARY
from .tools import tool_available as _tool_available
from .tools import preload_secondary as _preload_secondary

logger = logging.getLogger(__name__)

# Per-turn tool budget: 12 rounds x 3 tools (36 calls max). Chat turns are
# interactive, so rounds stay well below the resume-review budget (18x4);
# 12 rounds leave headroom for GitHub deep-dives (readme -> file -> commits)
# while the loop's last-round wrap-up hint still forces a timely close.
# Width stays at 3: wider parallel batches invite junk calls in chat context.
_MAX_TOOL_ROUNDS = 12
_MAX_TOOLS_PER_ROUND = 3
# Fallback value when context window is unknown
_FALLBACK_CONTEXT_TOKENS = DEFAULT_CONTEXT_WINDOW
# Whole-turn budget: bounds worker + DB-session hold time. Worst case without
# it is 12 rounds x (an LLM call + up to 3x18s tools + compression) — tens of
# minutes. On timeout the tool loop aborts and the caller falls back to a
# closing answer.
_TURN_TIMEOUT_SECONDS = 600.0
# Tool-observation compression budget. The platform default (120s) targets batch
# jobs; interactive chat converges to 30s so one slow blob cannot stall a turn.
_COMPRESSION_TIMEOUT_SECONDS = 30.0

# Complete toolset handed to the model = ask_user + domain tool registry.
PREP_TOOL_DEFINITIONS: list[dict[str, Any]] = [ASK_USER_TOOL, *_DOMAIN_TOOL_DEFS]

# Absolute usage floor below which the agent-invoked compact tool refuses to
# run (tiny sessions have nothing worth an extra summarizer call).
_COMPACT_TOOL_MIN_RATIO = 0.3
# Per-turn memory_write budget: LLM owns dedup decisions, this only stops
# runaway loops from spamming the store. Distinct facts should be batched
# into fewer calls.
_MAX_MEMORY_WRITES_PER_TURN = 2


def _prefix_fingerprint(
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


class PrepAgent:
    def __init__(self, session: PrepSession, llm: LLMClient):
        self.session = session
        self.llm = llm
        # Context window for model entry declarations; falls back to old value when unknown
        self.context_window = getattr(llm, "context_window", 0) or _FALLBACK_CONTEXT_TOKENS
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
        """Context assembly for the model: LLM-generated summary compaction + working-memory injection.

        Compaction occurs only at the start of each conversation turn (and may trigger one LLM summary call); the persistence path
        (chat.finalize) uses rule-based compaction and adds no latency while saving.
        ``threshold`` carries the user's auto-compact setting (``None`` = agent-decided default);
        ``force`` (manual ``/compact``) always attempts an LLM summary.
        ``options`` carries intensity/directive/retain; ``keep_from`` pins the
        verbatim cutoff for mid-turn agent-invoked compaction; ``provenance``
        stamps the new summary trailer; ``report`` collects compaction cost
        without raising.
        """
        working = await build_working_context(
            self.messages, self.context_window, memory=self.memory, llm=self.llm,
            reply_locale=self.reply_locale, threshold=threshold, force=force,
            options=options, keep_from=keep_from, provenance=provenance, report=report,
            default_focus=self._objective_line or None,
        )
        self.last_prefix_fingerprint = _prefix_fingerprint(working, self._tool_definitions())
        return working

    def _tool_definitions(self, user_text: str = "") -> list[dict[str, Any]]:
        """Per-turn model toolset: tier-1 + turn-relevant tools, then compact.

        Secondary-tier specs stay out of the initial declarations UNLESS a
        name-gated signal matches (repo talk preloads github tools) — decided
        once at turn start, frozen for the round, so the cached prefix head
        never reorders. Anything else secondary loads through ``search_tools``.
        The returned list is stored as ``_turn_tools`` and handed to the loop
        by reference — mid-turn expansion only appends.
        """
        resume_id = getattr(self.session, "resume_id", None)
        primary: list[dict[str, Any]] = []
        preloaded: list[dict[str, Any]] = []
        for item in [ASK_USER_TOOL, *_DOMAIN_TOOL_DEFS]:
            name = ""
            try:
                name = str((item.get("function") or {}).get("name") or "")
            except Exception:
                name = ""
            if not name:
                continue
            spec = _TOOL_REGISTRY.get(name)
            if spec is not None and spec.tier == _TIER_SECONDARY:
                # On-demand tier: preload only on a matched signal gate (repo
                # talk); pure on-demand tools wait for search_tools.
                if _preload_secondary(name, user_text, resume_id):
                    preloaded.append(item)
                continue
            if not _tool_available(name, user_text, resume_id):
                continue
            primary.append(item)
        declared = [*primary, *preloaded]
        # Static compact-tool declaration: the live usage estimate moved to the
        # per-turn [Context usage] system suffix (build_working_context) — a
        # per-turn tool description would sit at the head of the provider
        # request and invalidate the whole prompt-cache prefix every turn.
        declared.append(_COMPACT_TOOL_DEFINITION)
        self._turn_state.tools = declared
        return declared

    def _expand_turn_tools(self, selected: list[str]) -> list[str]:
        """Append on-demand schemas to the live turn toolset. Returns names added."""
        added: list[str] = []
        if self._turn_state.tools is None:
            return added
        try:
            present = {
                str((item.get("function") or {}).get("name") or "")
                for item in self._turn_state.tools
            }
        except Exception:
            present = set()
        for name in selected:
            if name in present or name not in _SECONDARY_DEFINITIONS:
                continue
            self._turn_state.tools.append(_SECONDARY_DEFINITIONS[name])
            present.add(name)
            added.append(name)
        return added

    async def _compact_current_round(
        self, args: dict[str, Any], db: Session
    ) -> tuple[str, list[SearchHit]]:
        """Agent-invoked mid-turn compaction (the ``compact_context`` tool body).

        Folds everything before the current user message into an LLM summary
        and persists immediately; the in-flight tool round continues on its
        working copy and chat.finalize merges the new tail back on top (so
        tool-call pairing never splits). Guarded: once per turn, and refused
        below an absolute usage floor. Per-call ``focus``/``intensity`` args
        override the turn policy for this run only (validated, never raising).
        """
        call_args = args if isinstance(args, dict) else {}
        if self._turn_state.compact_used:
            return "Compaction already ran this turn; continuing with the compacted context.", []
        window = self.context_window or _FALLBACK_CONTEXT_TOKENS
        usage = estimate_messages_tokens(self.messages)
        if window > 0 and usage <= window * _COMPACT_TOOL_MIN_RATIO:
            return (
                f"Compaction not needed yet (usage ~{usage} tokens is below the "
                "minimum for a summarizer call); continuing with full history. "
                "Do not call compact_context again this turn.",
                [],
            )
        rest = [m for m in self.messages if isinstance(m, dict) and m.get("role") != "system"]
        last_user = max(
            (i for i, m in enumerate(rest) if m.get("role") == "user"),
            default=-1,
        )
        if last_user < 0:
            return "No user turn to protect yet; compaction refused.", []
        before = usage
        report: dict[str, Any] = {}
        policy = CompactionOptions.resolve(
            intensity=call_args.get("intensity"),
            directive=call_args.get("focus"),
            default=self._turn_state.policy,
        )
        try:
            compacted = await self._build_context(
                force=True, options=policy, keep_from=last_user, report=report,
            )
        except Exception as e:
            safe_detail = redact_api_key(str(e))[:200]
            logger.warning("Agent-invoked compaction failed: %s", safe_detail)
            return f"Compaction failed ({safe_detail}); continuing with full history.", []
        self._turn_state.compact_used = True
        self._turn_state.mid_turn_base = compacted
        self.messages = compacted
        self._save(db)
        after = estimate_messages_tokens(self.messages)
        self._turn_state.mid_turn_report = {
            "before": before,
            "after": after,
            "summarized": True,
            "prompt_tokens": int(report.get("prompt_tokens", 0)),
            "completion_tokens": int(report.get("completion_tokens", 0)),
            "latency_ms": round(float(report.get("latency_ms", 0.0)), 1),
        }
        return (
            f"Context compacted by summarizer ({policy.intensity}"
            + (f", focus: {policy.directive}" if policy.directive else "")
            + f"): ~{before} → ~{after} tokens. "
            "Older turns are now a sectioned summary; the current turn continues unchanged.",
            [],
        )

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
            if self._turn_state.memory_writes >= _MAX_MEMORY_WRITES_PER_TURN:
                return (
                    f"memory_write budget exhausted this turn (max {_MAX_MEMORY_WRITES_PER_TURN}); "
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
        """Tool loop. Returns ``(messages, early_content, search_groups, tool_steps, thinking)``.

        ``content_state`` (streaming path only) enables speculative content streaming;
        the caller owns the dict and flushes the sanitizer's held-back tail afterwards.
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
        """Synchronous single-round reply (see :mod:`chat` for arrangement and storage)."""
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
