"""StepFun backend tests for src/realmock/domains/interview/capabilities/rag/stepfun_backend.py.

Covers: empty/tool-shape/query/ensure-index/jsonl serialize (no network)
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from realmock.domains.interview.agents.tool_round_runner import (
    ToolRoundRunner,
)
from realmock.domains.interview.capabilities.rag.stepfun_backend import (
    StepFunRetrievalRAG,
    _serialize_documents_to_jsonl,
)
from realmock.platform.config import Settings
from realmock.platform.core.ratelimit import reset_rate_limit
from tests.fakes import FakeLLMClient


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


def test_stepfun_is_empty_and_tool_none() -> None:
    rag = StepFunRetrievalRAG(llm=FakeLLMClient(api_key=""), settings=_settings())
    assert rag.is_empty() is True
    assert rag.build_retrieval_tool() is None


def test_stepfun_ready_tool_shape_extra() -> None:
    rag = StepFunRetrievalRAG(llm=FakeLLMClient(api_key="x"), settings=_settings())
    rag._vector_store_id = "vs-1"
    rag._ready = True
    tool = rag.build_retrieval_tool()
    assert tool is not None
    assert tool["function"]["options"]["vector_store_id"] == "vs-1"


@pytest.mark.asyncio
async def test_stepfun_query_always_empty() -> None:
    rag = StepFunRetrievalRAG(llm=FakeLLMClient(api_key="x"), settings=_settings())
    assert await rag.query("q") == []
    assert await rag.query_for_company("q", "bytedance") == []


@pytest.mark.asyncio
async def test_stepfun_ensure_index_no_key_skips() -> None:
    rag = StepFunRetrievalRAG(llm=FakeLLMClient(api_key=""), settings=_settings())
    await rag.ensure_index()
    assert rag.is_empty() is True


@pytest.mark.asyncio
async def test_stepfun_ensure_index_unsafe_url_skips() -> None:
    from realmock.platform.core.security import UnsafeURLError

    rag = StepFunRetrievalRAG(llm=FakeLLMClient(api_key="k"), settings=_settings())
    with patch(
        "realmock.domains.interview.capabilities.rag.stepfun_backend.assert_safe_http_url",
        side_effect=UnsafeURLError("unsafe"),
    ):
        await rag.ensure_index()
    assert rag.is_empty() is True


@pytest.mark.asyncio
async def test_stepfun_ensure_index_create_flow() -> None:
    rag = StepFunRetrievalRAG(llm=FakeLLMClient(api_key="k"), settings=_settings())
    assert rag._vector_store_id is None
    with (
        patch(
            "realmock.domains.interview.capabilities.rag.stepfun_backend.assert_safe_http_url",
            return_value=None,
        ),
        patch.object(rag._index_http, "create_vector_store", new=AsyncMock(return_value="vs-new")),
        patch.object(rag._index_http, "upload_kb_file", new=AsyncMock(return_value="file-1")),
        patch.object(rag._index_http, "attach_file", new=AsyncMock()),
    ):
        await rag.ensure_index()
    assert rag._ready is True
    assert rag._vector_store_id == "vs-new"


def test_serialize_jsonl_lines() -> None:
    raw = _serialize_documents_to_jsonl()
    assert raw.endswith(b"\n")
    assert len(raw.decode("utf-8").splitlines()) > 10
