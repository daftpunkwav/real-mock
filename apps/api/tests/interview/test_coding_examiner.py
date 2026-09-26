"""Coding examiner tests for src/realmock/domains/interview/agents/topology/coding_examiner.py.

Covers: challenge create/evaluate fallbacks, score clamping, memory recording
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

import pytest

from realmock.domains.interview.agents.memory.cognitive_graph import (
    CognitiveMemoryGraph,
    CompetencyStatus,
)
from realmock.domains.interview.agents.topology.coding_examiner import (
    CodeEvaluationReport,
    CodingChallenge,
    CodingExaminerAgent,
    CodingTestCase,
)
from realmock.platform.capabilities.ai.llm.client import LLMClient


def _fallback_llm() -> LLMClient:
    return LLMClient(api_base="https://api.example.com", api_key="", model="gpt-4")


def test_coding_testcase_and_challenge_to_dict() -> None:
    tc = CodingTestCase(input="1", expected="2", is_hidden=True, description="d")
    assert tc.to_dict() == {"input": "1", "expected": "2", "is_hidden": True, "description": "d"}
    ch = CodingChallenge(
        id="c1", title="T", description="D", language="python",
        starter_code="pass", test_cases=[tc],
    )
    d = ch.to_dict()
    assert d["id"] == "c1" and d["language"] == "python"
    assert d["test_cases"][0]["input"] == "1"
    rep = CodeEvaluationReport(passed=True, score=8)
    assert rep.to_dict()["score"] == 8


@pytest.mark.asyncio
async def test_create_challenge_empty_key_fallback() -> None:
    graph = CognitiveMemoryGraph()
    agent = CodingExaminerAgent(_fallback_llm(), graph)
    ch = await agent.create_challenge(role="Backend", level="Senior", preferred_language="python")
    assert ch.id == "two_sum_variant"
    assert ch.language == "python"
    assert agent.active_challenge is ch
    assert graph.working_memory.active_code_task == ch.title
    assert len(ch.test_cases) == 2


@pytest.mark.asyncio
async def test_create_challenge_respects_language() -> None:
    agent = CodingExaminerAgent(_fallback_llm(), CognitiveMemoryGraph())
    ch = await agent.create_challenge(preferred_language="javascript")
    assert ch.language == "javascript"


@pytest.mark.asyncio
async def test_create_challenge_llm_success(monkeypatch) -> None:
    import realmock.domains.interview.agents.topology.coding_examiner as mod
    from tests.fakes import FakeLLMClient

    monkeypatch.setattr(mod, "CODING_CHALLENGE_PROMPT", "role {role} level {level}")
    payload = {
        "id": "slug-1",
        "title": "Sum It",
        "description": "Add numbers",
        "language": "python",
        "starter_code": "def f(): pass",
        "test_cases": [
            {"input": "1", "expected": "1", "is_hidden": False, "description": "a"},
            "not-a-dict",
        ],
    }

    class _Shim(FakeLLMClient):
        async def chat_json(self, messages, temperature=0.3):  # type: ignore[override]
            return payload

    shim = _Shim(json_payload=payload, api_key="k")
    agent = CodingExaminerAgent(shim, CognitiveMemoryGraph())  # type: ignore[arg-type]
    ch = await agent.create_challenge(preferred_language="python")
    assert ch.id == "slug-1"
    assert ch.title == "Sum It"
    assert len(ch.test_cases) == 1
    assert agent.active_challenge is ch


@pytest.mark.asyncio
async def test_create_challenge_prompt_format_reaches_llm() -> None:
    # JSON example braces are escaped, so .format renders and the LLM is
    # reached (previously a KeyError propagated before any network call).
    from tests.fakes import FakeLLMClient

    reached = {"n": 0}

    class _Reached(FakeLLMClient):
        async def chat_json(self, messages, temperature=0.3):  # type: ignore[override]
            reached["n"] += 1
            return None

    agent = CodingExaminerAgent(_Reached(api_key="k"), CognitiveMemoryGraph())  # type: ignore[arg-type]
    ch = await agent.create_challenge(preferred_language="python")
    assert reached["n"] == 1
    # A None payload degrades to the static fallback challenge.
    assert ch.id == "lru_cache_lite"


@pytest.mark.asyncio
async def test_create_challenge_invalid_llm_json_uses_exception_fallback(monkeypatch) -> None:
    import realmock.domains.interview.agents.topology.coding_examiner as mod
    from tests.fakes import FakeLLMClient

    monkeypatch.setattr(mod, "CODING_CHALLENGE_PROMPT", "role {role} level {level}")

    class _Bad(FakeLLMClient):
        async def chat_json(self, messages, temperature=0.3):  # type: ignore[override]
            return None  # type: ignore[return-value]

    agent = CodingExaminerAgent(_Bad(api_key="k"), CognitiveMemoryGraph())  # type: ignore[arg-type]
    ch = await agent.create_challenge(preferred_language="python")
    assert ch.id == "lru_cache_lite"
    assert "LRU" in ch.title


@pytest.mark.asyncio
async def test_create_challenge_llm_raises_uses_exception_fallback(monkeypatch) -> None:
    import realmock.domains.interview.agents.topology.coding_examiner as mod
    from tests.fakes import FakeLLMClient

    monkeypatch.setattr(mod, "CODING_CHALLENGE_PROMPT", "role {role} level {level}")

    class _Boom(FakeLLMClient):
        async def chat_json(self, messages, temperature=0.3):  # type: ignore[override]
            raise RuntimeError("boom")

    agent = CodingExaminerAgent(_Boom(api_key="k"), CognitiveMemoryGraph())  # type: ignore[arg-type]
    ch = await agent.create_challenge(preferred_language="typescript")
    assert ch.id == "lru_cache_lite"
    assert ch.language == "typescript"


@pytest.mark.asyncio
async def test_evaluate_prompt_format_reaches_llm() -> None:
    from tests.fakes import FakeLLMClient

    reached = {"n": 0}

    class _Reached(FakeLLMClient):
        async def chat_json(self, messages, temperature=0.3):  # type: ignore[override]
            reached["n"] += 1
            return None

    agent = CodingExaminerAgent(_Reached(api_key="k"), CognitiveMemoryGraph())  # type: ignore[arg-type]
    rep = await agent.evaluate_submission(code="x", test_output="y", turn_index=6)
    assert reached["n"] == 1
    # A None payload degrades to the flagged-error report.
    assert rep.error is True


@pytest.mark.asyncio
async def test_evaluate_submission_empty_key_fallback() -> None:
    agent = CodingExaminerAgent(_fallback_llm(), CognitiveMemoryGraph())
    rep = await agent.evaluate_submission(code="def f(): pass", test_output="ok", turn_index=1)
    assert rep.passed is True
    assert rep.score == 7
    assert "executed" in rep.summary


@pytest.mark.asyncio
async def test_evaluate_submission_clamps_high_score_and_records_verified(monkeypatch) -> None:
    import realmock.domains.interview.agents.topology.coding_examiner as mod
    from tests.fakes import FakeLLMClient

    monkeypatch.setattr(
        mod, "CODE_EVAL_PROMPT",
        "desc {problem_description} lang {language} code {code} out {test_output}",
    )

    payload = {
        "passed": True, "score": 99, "time_complexity": "O(n)",
        "space_complexity": "O(1)", "summary": "great",
        "feedback_for_candidate": "nice", "strengths": ["clean", 42, None],
        "weaknesses": ["slow"],
    }

    class _Shim(FakeLLMClient):
        async def chat_json(self, messages, temperature=0.3):  # type: ignore[override]
            return payload

    graph = CognitiveMemoryGraph()
    agent = CodingExaminerAgent(_Shim(api_key="k"), graph)  # type: ignore[arg-type]
    rep = await agent.evaluate_submission(code="x", test_output="y", turn_index=2)
    assert rep.score == 10
    assert rep.passed is True
    assert "clean" in rep.strengths and "42" in rep.strengths
    node = graph.nodes.get("live coding implementation")
    assert node is not None
    assert node.status == CompetencyStatus.VERIFIED


@pytest.mark.asyncio
async def test_evaluate_submission_clamps_low_and_bad_score_type(monkeypatch) -> None:
    import realmock.domains.interview.agents.topology.coding_examiner as mod
    from tests.fakes import FakeLLMClient

    monkeypatch.setattr(
        mod, "CODE_EVAL_PROMPT",
        "desc {problem_description} lang {language} code {code} out {test_output}",
    )

    for raw_score, expected in ((0, 1), (-5, 1), ("bad", 5), (None, 5)):
        payload = {"passed": False, "score": raw_score, "summary": "s"}

        class _Shim(FakeLLMClient):
            async def chat_json(self, messages, temperature=0.3):  # type: ignore[override]
                return dict(payload)

        graph = CognitiveMemoryGraph()
        agent = CodingExaminerAgent(_Shim(api_key="k"), graph)  # type: ignore[arg-type]
        rep = await agent.evaluate_submission(code="x", test_output="y", turn_index=3)
        assert rep.score == expected
        assert rep.passed is False


@pytest.mark.asyncio
async def test_evaluate_submission_failed_status_recorded(monkeypatch) -> None:
    import realmock.domains.interview.agents.topology.coding_examiner as mod
    from tests.fakes import FakeLLMClient

    monkeypatch.setattr(
        mod, "CODE_EVAL_PROMPT",
        "desc {problem_description} lang {language} code {code} out {test_output}",
    )

    payload = {"passed": False, "score": 3, "summary": "weak"}

    class _Shim(FakeLLMClient):
        async def chat_json(self, messages, temperature=0.3):  # type: ignore[override]
            return dict(payload)

    graph = CognitiveMemoryGraph()
    agent = CodingExaminerAgent(_Shim(api_key="k"), graph)  # type: ignore[arg-type]
    rep = await agent.evaluate_submission(code="x", test_output="y", turn_index=4)
    assert rep.score == 3
    node = graph.nodes.get("live coding implementation")
    assert node is not None
    assert node.status == CompetencyStatus.FAILED


@pytest.mark.asyncio
async def test_evaluate_submission_exception_fallback(monkeypatch) -> None:
    import realmock.domains.interview.agents.topology.coding_examiner as mod
    from tests.fakes import FakeLLMClient

    monkeypatch.setattr(
        mod, "CODE_EVAL_PROMPT",
        "desc {problem_description} lang {language} code {code} out {test_output}",
    )

    class _Boom(FakeLLMClient):
        async def chat_json(self, messages, temperature=0.3):  # type: ignore[override]
            raise RuntimeError("llm down")

    agent = CodingExaminerAgent(_Boom(api_key="k"), CognitiveMemoryGraph())  # type: ignore[arg-type]
    rep = await agent.evaluate_submission(code="x", test_output="y", turn_index=5)
    assert rep.passed is False
    assert rep.score == 5
    assert "error" in rep.summary.lower()


@pytest.mark.asyncio
async def test_evaluate_submission_stores_code_in_memory() -> None:
    agent = CodingExaminerAgent(_fallback_llm(), CognitiveMemoryGraph())
    await agent.evaluate_submission(code="CODE", test_output="OUT", turn_index=1)
    assert agent.memory_graph.working_memory.candidate_code == "CODE"
    assert agent.memory_graph.working_memory.last_test_output == "OUT"


# ---- reflection ----















# ---- entry clipping and error flag ----


@pytest.mark.asyncio
async def test_evaluate_submission_clips_oversized_input() -> None:
    from realmock.domains.interview.agents.topology.coding_examiner import (
        EVAL_CODE_MAX_CHARS,
        EVAL_OUTPUT_MAX_CHARS,
    )

    graph = CognitiveMemoryGraph()
    agent = CodingExaminerAgent(_fallback_llm(), graph)
    await agent.evaluate_submission(
        code="x" * (EVAL_CODE_MAX_CHARS + 5000),
        test_output="y" * (EVAL_OUTPUT_MAX_CHARS + 5000),
        turn_index=1,
    )
    assert len(graph.working_memory.candidate_code) == EVAL_CODE_MAX_CHARS
    assert len(graph.working_memory.last_test_output) == EVAL_OUTPUT_MAX_CHARS


@pytest.mark.asyncio
async def test_evaluate_submission_error_flagged(monkeypatch) -> None:
    graph = CognitiveMemoryGraph()
    agent = CodingExaminerAgent(_fallback_llm(), graph)

    async def _boom(*args, **kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(agent.llm, "api_key", "sk-test", raising=False)
    monkeypatch.setattr(agent.llm, "chat_json", _boom, raising=False)
    report = await agent.evaluate_submission(code="c", test_output="t", turn_index=1)
    assert report.error is True
    assert report.passed is False
    assert "error" in report.to_dict()


# ---- prompt templates must render through .format (JSON braces escaped) ----


def test_prompt_templates_render_without_key_error() -> None:
    from realmock.domains.interview.agents.topology.prompts import (
        CODE_EVAL_PROMPT,
        CODING_CHALLENGE_PROMPT,
    )

    challenge = CODING_CHALLENGE_PROMPT.format(role="Backend", level="Senior")
    assert "{role}" not in challenge
    assert '"challenge_slug"' in challenge
    rendered = CODE_EVAL_PROMPT.format(
        problem_description="P", language="python", code="c", test_output="t"
    )
    assert '"passed": true' in rendered


@pytest.mark.asyncio
async def test_create_challenge_llm_path_succeeds(monkeypatch) -> None:
    graph = CognitiveMemoryGraph()
    agent = CodingExaminerAgent(_fallback_llm(), graph)
    payload = {
        "id": "c1",
        "title": "T",
        "description": "D",
        "language": "python",
        "starter_code": "pass",
        "test_cases": [{"input": "1", "expected": "2"}],
    }

    async def _json(*args, **kwargs):
        return payload

    monkeypatch.setattr(agent.llm, "api_key", "sk-test", raising=False)
    monkeypatch.setattr(agent.llm, "chat_json", _json, raising=False)
    ch = await agent.create_challenge(preferred_language="python")
    assert ch.id == "c1"
    assert agent.active_challenge is ch
