"""Interview turn: tool-round executor (function-calling loop).

Extracted from InterviewRunner. Collects tools (StepFun retrieval + interview
function tools), runs up to N tool rounds, and records ledger tool previews
on ``agent.agent_state["_pending_ledger_tools"]`` alongside learning tool_trace.

Speculative streaming: with a ``content_sink`` provided, body-text deltas of
post-tool rounds are parsed through the say-first protocol live and forwarded
as TOKEN events, so the final answer streams while the loop is still running.
Pre-tool rounds stay buffered (a direct first answer is burst-emitted by the
caller's early path — drift-safe, mirroring the platform loop's gating).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from sqlalchemy.orm import Session

from realmock.domains.interview.capabilities.rag.company_rag import (
    CompanyKnowledgeRAG,
    format_context as format_rag_context,
)
from realmock.domains.interview.ledger.store import append_pending_tool, begin_pending_tools, build_tool_preview
from realmock.domains.interview.agents.agent_text import ThinkStreamFilter
from realmock.domains.interview.agents.events import StreamEvent
from realmock.domains.interview.agents.session_state import InterviewSessionState
from realmock.domains.interview.agents.tools import (
    MAX_TOOL_ROUNDS,
    execute_interview_tool,
    get_interview_tool_definitions,
)
from realmock.domains.interview.agents.tool_guard import ToolGuard
from realmock.domains.interview.agents.turn_output import TurnOutput, parse_turn_output
from realmock.platform.capabilities.ai.agent import run_agent_loop
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.capabilities.ai.llm.say_first_stream import SayFirstStreamParser
from realmock.platform.config import get_settings
from realmock.platform.core.constants import RAGBackendKind

logger = logging.getLogger(__name__)

# Whole-loop wall-clock budget: bounds worst case (N rounds x an LLM call plus
# tool execution time) so one turn cannot hold the request-scoped DB session
# for tens of minutes. Individual tools have no per-call timeout here; the
# platform loop converts tool exceptions into observations.
_TOOL_ROUND_BUDGET_SECONDS = 600.0


@dataclass
class ToolRoundResult:
    """Outcome of one tool-round run.

    ``early`` is the loop's final content when a round answered without tool
    calls. ``streamed_output`` is set only when say tokens were already
    forwarded live through the content sink — the caller must not re-emit the
    say text and uses this TurnOutput for the control fields.
    """

    messages: list[dict[str, Any]]
    early: str | None
    streamed_output: TurnOutput | None = None


class ToolRoundRunner:
    """Non-streaming tool loop: execute tool_calls for up to N rounds (one per session)."""

    def __init__(
        self,
        session,
        llm: LLMClient,
        agent: InterviewSessionState,
        rag: CompanyKnowledgeRAG | None,
    ) -> None:
        self.session = session
        self.llm = llm
        self.agent = agent
        self.rag = rag
        # One guard per session: breaker streaks persist in agent_state across
        # turns, so a chronically broken tool stays open without re-burning.
        self.guard = ToolGuard(
            state_fn=lambda: self.agent.agent_state,
            error_context={"domain": "interview", "session": getattr(session, "id", None)},
        )

    async def maybe_retrieve_rag(
        self,
        query: str,
        *,
        top_k: int = 3,
    ) -> dict[str, str] | None:
        """Retrieve through the RAG instance if present; return a system message that can be injected into messages, or None.

        - If RAG is not configured, the index is empty, or the API fails: return None (without affecting the main flow)
        - Log a warning on retrieval failure; do not raise an exception
        """
        if self.rag is None or not query:
            return None
        # The StepFun backend does not return locally matched snippets (actual retrieval is performed by the StepFun server during chat),
        # Return None directly here and let :meth:`collect_chat_tools` inject the retrieval tool.
        if getattr(self.rag, "kind", None) == RAGBackendKind.STEPFUN:
            return None
        try:
            company_id = self.session.company or None
            hits = await self.rag.query_for_company(
                query, company_id, top_k=top_k
            ) if company_id else await self.rag.query(query, top_k=top_k)
        except Exception as e:
            logger.warning("RAG retrieval failed: %s", e)
            return None

        if not hits:
            return None

        # Filter weak matches that are too far apart
        hits = [h for h in hits if h.get("distance", 1.0) < 0.5]
        if not hits:
            return None

        logger.info(
            "RAG hits: session=%s company=%s hits=%d",
            self.session.id, self.session.company, len(hits),
        )
        return {
            "role": "system",
            "content": format_rag_context(hits),
        }

    def collect_chat_tools(self, *, include_function_tools: bool = True) -> list[dict[str, Any]] | None:
        """Collect the tools to inject into the current LLM call.

        Combines:
        1. StepFun retrieval tool (if supported by the RAG backend);
        2. Interview function tools (GitHub / company / résumé / interview-experience search);
        3. Cross-round record tools when inside a process with finished earlier rounds.
        """
        tools: list[dict[str, Any]] = []
        if self.rag is not None:
            builder = getattr(self.rag, "build_retrieval_tool", None)
            if builder is not None:
                tool = builder()
                if tool:
                    tools.append(tool)
        settings = get_settings()
        if include_function_tools and settings.interview_tools_enabled:
            from realmock.domains.interview.agents.past_records import has_prior_rounds
            from realmock.platform.database import sessions_db_session

            with sessions_db_session() as sessions_db:
                include_past = has_prior_rounds(sessions_db, self.session)
            tools.extend(
                get_interview_tool_definitions(include_past_records=include_past)
            )
        return tools or None

    async def run_tool_rounds(
        self,
        api_messages: list[dict[str, Any]],
        db: Session,
        *,
        temperature: float = 0.75,
        content_sink: Callable[[StreamEvent], Awaitable[None]] | None = None,
    ) -> ToolRoundResult:
        """Non-streaming tool loop: execute tool_calls for at most N rounds.

        With ``content_sink``, say-first text deltas of POST-tool rounds are
        parsed incrementally (think filter → SayFirstStreamParser) and forwarded
        as TOKEN events while the loop runs; the returned ``streamed_output``
        then carries the turn's control fields. Pre-tool content stays buffered.

        Returns:
            ToolRoundResult with ``(messages, early, streamed_output)``:
            - streamed_output set: the say text already went out live; the
              caller skips regeneration and uses its control fields;
            - early set without streaming: a direct first answer — the caller
              burst-emits it (parse_complete_output), avoiding a second call;
            - neither: the caller generates via streaming (say-first).
        """
        settings = get_settings()
        begin_pending_tools(self.agent.agent_state)
        if not settings.interview_tools_enabled:
            return ToolRoundResult(api_messages, None)

        max_rounds = min(settings.interview_max_tool_rounds, MAX_TOOL_ROUNDS)
        if max_rounds <= 0:
            return ToolRoundResult(api_messages, None)

        tools = self.collect_chat_tools(include_function_tools=True)
        if not tools:
            return ToolRoundResult(api_messages, None)

        # Speculative streaming state (say-first protocol aware): the platform
        # loop only forwards content deltas after the first tool round, so a
        # drift-retried pre-tool narration can never reach the sink twice.
        # Parser/think filter reset at every round boundary: a narration round
        # (say text + tool_calls) must not close the parser for the real final
        # answer in the next round.
        streamed = {"on": False}
        say_parts: list[str] = []
        state: dict[str, Any] = {}

        def _reset_round() -> None:
            state["think"] = ThinkStreamFilter()
            state["parser"] = SayFirstStreamParser()

        _reset_round()

        async def on_round_start() -> None:
            _reset_round()

        async def on_content(delta: str) -> None:
            visible = state["think"].feed(delta or "")
            if not visible or content_sink is None:
                return
            chunk = state["parser"].feed(visible)
            if chunk:
                streamed["on"] = True
                say_parts.append(chunk)
                await content_sink(StreamEvent.make_token(chunk))

        async def execute(name: str, args: dict[str, Any]) -> str:
            return await self.guard.run(
                name,
                args,
                lambda: execute_interview_tool(
                    name,
                    args,
                    db=db,
                    resume_id=self.session.resume_id,
                    profile_id=self.session.profile_id,
                    agent_state=self.agent.agent_state,
                    llm=self.llm,
                    session=self.session,
                ),
            )

        async def on_tool(name: str, args: dict[str, Any], result: str, tc_id: str) -> None:
            del tc_id
            from realmock.domains.interview.ledger.constants import is_tool_failure_result

            ok = not is_tool_failure_result(result if isinstance(result, str) else str(result))
            trace = self.agent.agent_state.setdefault("tool_trace", [])
            trace.append({"tool": name, "ok": ok})
            if len(trace) > 40:
                del trace[:-40]
            append_pending_tool(
                self.agent.agent_state,
                build_tool_preview(name, args, result, ok=ok),
            )
            logger.info("Tool call: session=%s tool=%s ok=%s", self.session.id, name, ok)

        try:
            loop = await asyncio.wait_for(
                run_agent_loop(
                    self.llm,
                    api_messages,
                    tools=tools,
                    execute=execute,
                    max_rounds=max_rounds,
                    temperature=temperature,
                    on_tool=on_tool,
                    on_content=on_content,
                    on_round_start=on_round_start,
                ),
                timeout=_TOOL_ROUND_BUDGET_SECONDS,
            )
        except asyncio.TimeoutError:
            if not streamed["on"]:
                # Degrade to the tools-disabled path: the caller streams a fresh
                # answer without tool enrichment instead of hanging the turn.
                logger.warning(
                    "Tool rounds exceeded %.0fs budget; session=%s falls back to plain streaming",
                    _TOOL_ROUND_BUDGET_SECONDS,
                    self.session.id,
                )
                return ToolRoundResult(api_messages, None)
            # Partial say already reached the user: complete the turn with it
            # instead of regenerating (which would duplicate what was heard).
            logger.warning(
                "Tool rounds exceeded %.0fs budget mid-stream; session=%s completes with the streamed partial",
                _TOOL_ROUND_BUDGET_SECONDS,
                self.session.id,
            )
            return ToolRoundResult(
                api_messages, None,
                await self._finish_streamed(state["parser"], say_parts, streamed, content_sink),
            )

        early = loop.final_content
        streamed_output = await self._finish_streamed(state["parser"], say_parts, streamed, content_sink)
        return ToolRoundResult(loop.messages, early, streamed_output)

    @staticmethod
    async def _finish_streamed(
        parser: SayFirstStreamParser,
        say_parts: list[str],
        streamed: dict[str, bool],
        content_sink: Callable[[StreamEvent], Awaitable[None]] | None,
    ) -> TurnOutput | None:
        """Flush the parser tail and assemble the streamed turn's output (None when nothing streamed)."""
        if not streamed["on"] or content_sink is None:
            return None
        tail = parser.finish()
        if tail:
            say_parts.append(tail)
            await content_sink(StreamEvent.make_token(tail))
        say_text = parser.raw_text if parser.degraded else "".join(say_parts)
        return parse_turn_output(parser.controls, say_text=say_text, degraded=parser.degraded)


__all__ = ["ToolRoundResult", "ToolRoundRunner"]
