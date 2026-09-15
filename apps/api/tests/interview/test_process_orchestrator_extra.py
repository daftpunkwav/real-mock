"""Process orchestrator tests for src/realmock/domains/interview/agents/topology/process_orchestrator.py.

Covers: time guards, no-key continue, LLM directives, bad/empty/exception fallbacks
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from realmock.domains.interview.agents.memory.cognitive_graph import (
    CognitiveMemoryGraph,
)
from realmock.domains.interview.agents.tool_round_runner import (
    ToolRoundRunner,
)
from realmock.domains.interview.agents.topology.process_orchestrator import (
    OrchestrationDirective,
    OrchestratorAdvice,
    ProcessOrchestratorAgent,
)
from realmock.platform.config import Settings
from realmock.platform.core.ratelimit import reset_rate_limit


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()


def _settings(**overrides) -> Settings:
    base = {
        "llm_api_base": "https://api.stepfun.com/v1",
        "llm_api_key": "sk-test",
        "llm_model": "step-3.7-flash",
        "rag_backend": "local",
    }
    base.update(overrides)
    return Settings(**base)


def _empty_llm() -> MagicMock:
    m = MagicMock()
    m.api_key = ""
    return m


# ---- process orchestrator ----


@pytest.mark.asyncio
async def test_orchestrator_time_guard_advances() -> None:
    agent = ProcessOrchestratorAgent(_empty_llm(), CognitiveMemoryGraph())
    advice = await agent.decide_next_step(
        current_phase="technical_deep", turn_index=5, elapsed_minutes=36.0
    )
    assert advice.directive == OrchestrationDirective.ADVANCE_PHASE


@pytest.mark.asyncio
async def test_orchestrator_time_guard_skips_summary() -> None:
    agent = ProcessOrchestratorAgent(_empty_llm(), CognitiveMemoryGraph())
    advice = await agent.decide_next_step(
        current_phase="summary", turn_index=5, elapsed_minutes=39.0
    )
    assert advice.directive == OrchestrationDirective.CONTINUE


@pytest.mark.asyncio
async def test_orchestrator_no_key_returns_continue() -> None:
    agent = ProcessOrchestratorAgent(_empty_llm(), CognitiveMemoryGraph())
    advice = await agent.decide_next_step(
        current_phase="technical_deep", turn_index=1, elapsed_minutes=2.0
    )
    assert advice.directive == OrchestrationDirective.CONTINUE
    assert advice.reason == "Standard flow progression."


@pytest.mark.asyncio
async def test_orchestrator_llm_directives() -> None:
    for directive in (
        "continue",
        "deepen_probe",
        "trigger_coding",
        "advance_phase",
        "conclude_interview",
    ):
        llm = MagicMock()
        llm.api_key = "k"
        llm.chat_json = AsyncMock(
            return_value={
                "directive": directive,
                "reason": "r",
                "target_topic": "t",
                "pacing_guidance": "p",
            }
        )
        agent = ProcessOrchestratorAgent(llm, CognitiveMemoryGraph())
        advice = await agent.decide_next_step(
            current_phase="tech", turn_index=2, elapsed_minutes=3.0
        )
        assert advice.directive == OrchestrationDirective(directive)
        assert advice.target_topic == "t"


@pytest.mark.asyncio
async def test_orchestrator_bad_directive_falls_back() -> None:
    llm = MagicMock()
    llm.api_key = "k"
    llm.chat_json = AsyncMock(return_value={"directive": "nonsense"})
    agent = ProcessOrchestratorAgent(llm, CognitiveMemoryGraph())
    advice = await agent.decide_next_step(current_phase="tech", turn_index=1, elapsed_minutes=1.0)
    assert advice.directive == OrchestrationDirective.CONTINUE


@pytest.mark.asyncio
async def test_orchestrator_empty_and_exception_fallback() -> None:
    llm = MagicMock()
    llm.api_key = "k"
    llm.chat_json = AsyncMock(return_value=None)
    agent = ProcessOrchestratorAgent(llm, CognitiveMemoryGraph())
    assert (
        await agent.decide_next_step(current_phase="tech", turn_index=1, elapsed_minutes=1.0)
    ).directive == OrchestrationDirective.CONTINUE
    llm2 = MagicMock()
    llm2.api_key = "k"
    llm2.chat_json = AsyncMock(return_value="not-a-dict")
    agent2 = ProcessOrchestratorAgent(llm2, CognitiveMemoryGraph())
    assert (
        await agent2.decide_next_step(current_phase="tech", turn_index=1, elapsed_minutes=1.0)
    ).directive == OrchestrationDirective.CONTINUE
    llm3 = MagicMock()
    llm3.api_key = "k"
    llm3.chat_json = AsyncMock(side_effect=RuntimeError("down"))
    agent3 = ProcessOrchestratorAgent(llm3, CognitiveMemoryGraph())
    assert isinstance(
        await agent3.decide_next_step(current_phase="tech", turn_index=1, elapsed_minutes=1.0),
        OrchestratorAdvice,
    )


# ---- tool round runner: rag + tools ----


def _runner(rag=None, llm=None) -> ToolRoundRunner:
    session = SimpleNamespace(id=1, company="bytedance", resume_id=None, profile_id=1)

    class _Agent:
        def __init__(self):
            self.agent_state = {}

    return ToolRoundRunner(session, llm or _empty_llm(), _Agent(), rag)  # type: ignore[arg-type]


































# ---- runner opening ----


def _opening_runner(**overrides):
    agent = MagicMock()
    agent.reload_plan = MagicMock()
    agent.reset_messages = MagicMock()
    agent.build_opening_prompt = MagicMock(return_value="system-prompt")
    agent.messages = []
    agent.agent_state = {}
    agent.record_assistant_text = MagicMock()
    agent.note_turn_output = MagicMock()
    agent.set_questions_in_phase = MagicMock()
    agent.mark_active = MagicMock()
    agent.save_state = MagicMock()
    agent.current_phase = MagicMock(return_value=SimpleNamespace(id="identity_check"))
    agent.advance_phase_if_needed = MagicMock(return_value=False)
    agent.phase_title_for_display = MagicMock(return_value="")
    runner = MagicMock()
    runner.session = SimpleNamespace(id=1)
    runner.agent = agent
    runner.llm = MagicMock(api_key="")
    runner.tools = MagicMock()
    runner.prompter = MagicMock()
    runner.prompter.get_context_window = MagicMock(return_value=None)
    for key, value in overrides.items():
        setattr(runner, key, value)
    return runner












# ---- stepfun backend ----














