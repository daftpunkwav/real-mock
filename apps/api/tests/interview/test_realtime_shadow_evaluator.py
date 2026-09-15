"""Shadow evaluator tests for agents/topology/shadow_evaluator.py.

Covers: empty text default, raw None/non-dict defaults, invalid score/topic/probe,
unknown status mapping, exception default.
Conventions: no real network/LLM (all external calls mocked); uses mocked LLM chat_json.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from realmock.domains.interview.agents.topology.shadow_evaluator import ShadowEvaluation, ShadowEvaluatorAgent

# No handler fixture: ShadowEvaluatorAgent is exercised with mocked LLM and memory graph.

@pytest.mark.asyncio
async def test_shadow_evaluator_gaps():
    from realmock.domains.interview.agents.memory import CognitiveMemoryGraph

    # empty text -> default
    g = CognitiveMemoryGraph()
    llm = MagicMock(api_key="sk")
    ag = ShadowEvaluatorAgent(llm, g)
    out = await ag.evaluate_turn(question="q", user_text="   ", current_phase="tech", turn_index=0)
    assert isinstance(out, ShadowEvaluation)
    # raw None -> default
    llm2 = MagicMock(api_key="sk")
    llm2.chat_json = AsyncMock(return_value=None)
    ag2 = ShadowEvaluatorAgent(llm2, CognitiveMemoryGraph())
    assert (await ag2.evaluate_turn(question="q", user_text="answer", current_phase="tech", turn_index=1)).substance_score == 5
    # raw not dict
    llm3 = MagicMock(api_key="sk")
    llm3.chat_json = AsyncMock(return_value=[1, 2])
    ag3 = ShadowEvaluatorAgent(llm3, CognitiveMemoryGraph())
    assert (await ag3.evaluate_turn(question="q", user_text="a", current_phase="tech", turn_index=1)).substance_score == 5
    # invalid score + valid topic + probe
    llm4 = MagicMock(api_key="sk")
    llm4.chat_json = AsyncMock(return_value={
        "substance_score": "bad", "is_consistent": False, "inconsistencies": ["x", 1, None],
        "technical_holes": ["hole1"], "suggested_probe": "probe me?",
        "should_trigger_coding": True, "assessed_topic": "Redis", "topic_status": "verified",
    })
    g4 = CognitiveMemoryGraph()
    ag4 = ShadowEvaluatorAgent(llm4, g4)
    ev = await ag4.evaluate_turn(question="q", user_text="ans", current_phase="tech", turn_index=2)
    assert ev.substance_score == 5
    assert ev.assessed_topic == "Redis"
    assert "probe me?" in g4.working_memory.pending_probes
    # unknown status -> UNTESTED, no holes -> score detail
    llm5 = MagicMock(api_key="sk")
    llm5.chat_json = AsyncMock(return_value={
        "substance_score": 99, "is_consistent": True, "inconsistencies": [], "technical_holes": [],
        "suggested_probe": "", "should_trigger_coding": False, "assessed_topic": "Raft", "topic_status": "weird",
    })
    ag5 = ShadowEvaluatorAgent(llm5, CognitiveMemoryGraph())
    ev5 = await ag5.evaluate_turn(question="q", user_text="ans", current_phase="tech", turn_index=3)
    assert ev5.substance_score == 10
    # exception -> default
    llm6 = MagicMock(api_key="sk")
    llm6.chat_json = AsyncMock(side_effect=RuntimeError("llm boom"))
    ag6 = ShadowEvaluatorAgent(llm6, CognitiveMemoryGraph())
    assert (await ag6.evaluate_turn(question="q", user_text="a", current_phase="tech", turn_index=1)).substance_score == 5

