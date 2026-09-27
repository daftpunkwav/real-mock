"""Interview turn executor: single entry for interview flow.

Opening / regular / closing streams live in child modules; this module keeps
InterviewRunner construction and public method delegation:

- :mod:`runner_opening` — opening stream
- :mod:`runner_turn` — regular turn stream
- :mod:`runner_closing` — closing stream

Subcomponents: PromptAssembler, ToolRoundRunner, InterviewSessionState.
System insights come from the platform contracts provider (composition root),
not a direct growth-domain import.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Any

from sqlalchemy.orm import Session

from realmock.domains.interview.capabilities.rag.company_rag import CompanyKnowledgeRAG
from realmock.domains.interview.models import InterviewSession
from realmock.domains.interview.agents.interviewer import (
    runner_closing,
    runner_opening,
    runner_turn,
)
from realmock.domains.interview.agents.events import EventKind, StreamEvent
from realmock.domains.interview.agents.prompt_assembler import PromptAssembler
from realmock.domains.interview.agents.session_state import InterviewSessionState
from realmock.domains.interview.agents.tool_round_runner import ToolRoundRunner
from realmock.domains.interview.agents.topology import ShadowEvaluatorAgent
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.contracts.lifecycle_hooks import get_system_insights_provider


class InterviewRunner:
    """Interview turn executor (one per session).

    Three streaming entry points delegate to child-module functions;
    prompter/tools are public for tests and external access.
    """

    def __init__(
        self,
        session: InterviewSession,
        llm: LLMClient,
        agent: InterviewSessionState | None = None,
        rag: CompanyKnowledgeRAG | None = None,
        task_spawner: Callable[[Coroutine[Any, Any, Any]], asyncio.Task[Any]] | None = None,
    ):
        self.session = session
        self.llm = llm
        self.agent = agent or InterviewSessionState(session, llm)
        self._task_spawner = task_spawner
        self._bg_tasks: set[asyncio.Task[Any]] = set()
        # True while a streaming flow (turn / closing) is mutating messages and
        # saving state. Background writers (step-compaction persist) check it
        # so their DB write can never interleave with the flow's ``save_state``.
        self.flow_active = False
        # Growth feedback port: composition root registers the provider.
        if self.agent.system_insights_provider is None:
            provider = get_system_insights_provider()
            if provider is not None:
                self.agent.system_insights_provider = provider
        self.rag = rag
        self.prompter = PromptAssembler(session, self.agent, llm)
        self.tools = ToolRoundRunner(session, llm, self.agent, rag)

        self._shadow_grounding_cache: str | None = None
        self.shadow_evaluator = ShadowEvaluatorAgent(
            llm, self.agent.cognitive_memory, context_provider=self._shadow_grounding
        )

    def _shadow_grounding(self) -> str:
        """Full candidate grounding for the shadow evaluator (cached once)."""
        if self._shadow_grounding_cache is None:
            try:
                from realmock.domains.interview.agents.agent_prompts import candidate_block

                profile = self.agent.get_user_profile(None)
                candidate = self.agent.get_candidate(None)
                self._shadow_grounding_cache = candidate_block(profile, candidate, compact=False)
            except Exception:
                self._shadow_grounding_cache = ""
        return self._shadow_grounding_cache

    def spawn_bg_task(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        """Spawn a background task bound to this runner or the injected spawner."""
        if self._task_spawner is not None:
            return self._task_spawner(coro)
        task = asyncio.create_task(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
        return task

    def agent_state_snapshot(self) -> dict[str, Any]:
        """Copy of the agent's working state for the realtime layer.

        Returns a copy so callers cannot mutate the internal dict through the
        facade; updates go through the dedicated write methods instead.
        """
        return dict(self.agent.agent_state)

    def record_interrupt_counts(self, *, candidate: int, ai: int) -> dict[str, Any]:
        """Record barge-in counters into the agent's working state.

        Single write path for the realtime layer. Returns the merged state
        dict so the caller can persist the same snapshot it just wrote.
        """
        state = self.agent.agent_state
        state["candidate_interrupts"] = candidate
        state["ai_interrupts"] = ai
        return dict(state)

    def message_history(self) -> list[Any]:
        """Shallow copy of the agent's message history.

        The list structure is copied; the message dicts themselves are shared,
        so content edits through the facade stay visible to the agent.
        """
        return list(self.agent.messages)

    async def cancel_bg_tasks(self) -> None:
        """Cancel all runner-owned background tasks."""
        tasks = list(self._bg_tasks)
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._bg_tasks.clear()

    async def stream_opening(self, db: Session) -> AsyncIterator[StreamEvent]:
        """Start the interview and stream the opening line."""
        async for event in runner_opening.stream_opening(self, db):
            yield event

    async def stream_turn(
        self,
        user_text: str,
        db: Session,
        *,
        face: dict[str, Any] | None = None,
        image_b64: str | None = None,
        followup_probe: str | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """Handle candidate replies and stream events."""
        self.flow_active = True
        try:
            async for event in runner_turn.stream_turn(
                self,
                user_text,
                db,
                face=face,
                image_b64=image_b64,
                followup_probe=followup_probe,
            ):
                yield event
        finally:
            self.flow_active = False

    async def stream_closing(self, db: Session) -> AsyncIterator[StreamEvent]:
        """Candidate-initiated close: verbal thanks + wrap-up, mark complete."""
        self.flow_active = True
        try:
            async for event in runner_closing.stream_closing(self, db):
                yield event
        finally:
            self.flow_active = False


__all__ = ["InterviewRunner", "StreamEvent", "EventKind"]
