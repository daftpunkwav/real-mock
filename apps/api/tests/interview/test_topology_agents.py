"""Unit tests for 4-Agent topology components."""

import pytest
from realmock.domains.interview.agents.memory import CognitiveMemoryGraph
from realmock.domains.interview.agents.topology import (
    CodingExaminerAgent,
    OrchestrationDirective,
    ProcessOrchestratorAgent,
    ShadowEvaluatorAgent,
)
from realmock.platform.capabilities.ai.llm.client import LLMClient


@pytest.mark.asyncio
async def test_shadow_evaluator_agent():
    graph = CognitiveMemoryGraph()
    llm = LLMClient(api_base="https://api.example.com", api_key="", model="gpt-4")  # Empty key triggers graceful fallback
    agent = ShadowEvaluatorAgent(llm, graph)

    evaluation = await agent.evaluate_turn(
        question="What is the difference between TCP and UDP?",
        user_text="TCP is connection oriented and reliable, while UDP is connectionless.",
        current_phase="technical_deep",
        turn_index=1,
    )
    assert evaluation is not None
    assert isinstance(evaluation.inconsistencies, list)


@pytest.mark.asyncio
async def test_coding_examiner_agent():
    graph = CognitiveMemoryGraph()
    llm = LLMClient(api_base="https://api.example.com", api_key="", model="gpt-4")
    agent = CodingExaminerAgent(llm, graph)

    challenge = await agent.create_challenge(
        role="Backend Engineer",
        level="Senior",
        preferred_language="python",
    )
    assert challenge is not None
    assert challenge.id
    assert challenge.language == "python"

    report = await agent.evaluate_submission(
        code="def solution(): return 1",
        test_output="Passed 1/1",
        turn_index=1,
    )
    assert report is not None
    assert report.score >= 0


@pytest.mark.asyncio
async def test_process_orchestrator_agent():
    graph = CognitiveMemoryGraph()
    llm = LLMClient(api_base="https://api.example.com", api_key="", model="gpt-4")
    agent = ProcessOrchestratorAgent(llm, graph)

    # Time budget limit triggers advance directive
    advice = await agent.decide_next_step(
        current_phase="technical_deep",
        turn_index=15,
        elapsed_minutes=36.0,
        target_duration_minutes=40.0,
    )
    assert advice.directive == OrchestrationDirective.ADVANCE_PHASE
