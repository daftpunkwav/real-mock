"""Unit tests for 4-Agent topology components."""

import pytest
from realmock.domains.interview.agents.memory import CognitiveMemoryGraph
from realmock.domains.interview.agents.topology import (
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


@pytest.mark.asyncio
async def test_shadow_three_phase_pipeline():
    """Phase 2 runs on the self-flag; phase 3 only when no probe came out."""

    from realmock.domains.interview.agents.topology.shadow_evaluator import ShadowEvaluatorAgent

    calls: list[str] = []

    class _PipelineLLM:
        api_key = "k"

        async def chat_json(self, messages, temperature=0.2):
            system = messages[0]["content"]
            if "second, stricter pass" in system:
                calls.append("recheck")
                return {
                    "substance_score": 6,
                    "assessed_topic": "caching",
                    "topic_status": "suspicious",
                    "suggested_probe": "how did you size the cache?",
                }
            if "probing question" in system:
                calls.append("probe")
                return {"probe": "what happens on a cold start?"}
            calls.append("evaluate")
            first = messages[1]["content"]
            if "evidence is thin" in first:
                return {
                    "substance_score": 4,
                    "evidence_insufficient": True,
                    "assessed_topic": "caching",
                    "topic_status": "suspicious",
                    "suggested_probe": "",
                }
            return {"substance_score": 7, "assessed_topic": "caching", "suggested_probe": "why LRU?"}

    agent = ShadowEvaluatorAgent(_PipelineLLM(), CognitiveMemoryGraph())
    res = await agent.evaluate_turn(
        question="Q",
        user_text="my answer mentions caching but the evidence is thin",
        current_phase="technical",
        turn_index=1,
    )
    assert res.substance_score == 6  # recheck overrode the first pass
    assert res.suggested_probe == "how did you size the cache?"
    assert calls == ["evaluate", "recheck"]  # probe phase not needed

    calls.clear()
    res2 = await agent.evaluate_turn(
        question="Q",
        user_text="solid caching answer",
        current_phase="technical",
        turn_index=2,
    )
    assert calls == ["evaluate"]  # no flag, probe present -> single call
    assert res2.suggested_probe == "why LRU?"
