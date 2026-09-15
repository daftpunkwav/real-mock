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

from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.orm import Session

from realmock.domains.interview.capabilities.rag.company_rag import CompanyKnowledgeRAG
from realmock.domains.interview.models import InterviewSession
from realmock.domains.interview.agents import runner_closing, runner_opening, runner_turn
from realmock.domains.interview.agents.events import EventKind, StreamEvent
from realmock.domains.interview.agents.prompt_assembler import PromptAssembler
from realmock.domains.interview.agents.session_state import InterviewSessionState
from realmock.domains.interview.agents.tool_round_runner import ToolRoundRunner
from realmock.domains.interview.agents.topology import (
    CodingExaminerAgent,
    ProcessOrchestratorAgent,
    ShadowEvaluatorAgent,
)
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
    ):
        self.session = session
        self.llm = llm
        self.agent = agent or InterviewSessionState(session, llm)
        # Growth feedback port: composition root registers the provider.
        if self.agent.system_insights_provider is None:
            provider = get_system_insights_provider()
            if provider is not None:
                self.agent.system_insights_provider = provider
        self.rag = rag
        self.prompter = PromptAssembler(session, self.agent, llm)
        self.tools = ToolRoundRunner(session, llm, self.agent, rag)

        self.shadow_evaluator = ShadowEvaluatorAgent(llm, self.agent.cognitive_memory)
        self.coding_examiner = CodingExaminerAgent(llm, self.agent.cognitive_memory)
        self.process_orchestrator = ProcessOrchestratorAgent(llm, self.agent.cognitive_memory)

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
        """Handle a candidate reply and stream events."""
        async for event in runner_turn.stream_turn(
            self,
            user_text,
            db,
            face=face,
            image_b64=image_b64,
            followup_probe=followup_probe,
        ):
            yield event

    async def stream_closing(self, db: Session) -> AsyncIterator[StreamEvent]:
        """Candidate-initiated close: verbal thanks + wrap-up, mark complete."""
        async for event in runner_closing.stream_closing(self, db):
            yield event


__all__ = ["InterviewRunner", "StreamEvent", "EventKind"]
