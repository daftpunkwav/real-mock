"""Report finalize tests for src/realmock/domains/records/agents/report/finalize.py.

Covers: _evidence_text flatten, repair_json fallbacks, finalize_json direct/repair
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from realmock.domains.records.agents.report.finalize import (
    _evidence_text,
    finalize_json,
    repair_json,
)
from realmock.platform.core.ratelimit import reset_rate_limit


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()


def _llm_empty() -> MagicMock:
    m = MagicMock()
    m.api_key = ""
    return m


# ---- finalize ----


def test_evidence_text_flattens_tools_and_draft() -> None:
    msgs = [
        {"role": "tool", "content": "  obs1  ", "name": "ledger_read_turns"},
        {"role": "assistant", "content": "thinking"},
        {"role": "tool", "content": "", "name": "x"},
        {"role": "tool", "content": "obs2"},
    ]
    text = _evidence_text(msgs, "draft here")
    assert "TOOL_ledger_read_turns" in text
    assert "DRAFT" in text
    assert _evidence_text([{"role": "user", "content": "hi"}], "") == ""


@pytest.mark.asyncio
async def test_repair_json_no_evidence_returns_none() -> None:
    assert (
        await repair_json(
            _llm_empty(), [{"role": "user", "content": "hi"}], "", schema_text="{}", purpose="p"
        )
        is None
    )


@pytest.mark.asyncio
async def test_repair_json_compress_fallback_and_success() -> None:
    llm = _llm_empty()
    llm.chat_json = AsyncMock(return_value={"overall_score": 80})
    with patch(
        "realmock.domains.records.agents.report.finalize.compress_text_blob",
        new=AsyncMock(side_effect=RuntimeError("compress down")),
    ):
        out = await repair_json(
            llm,
            [{"role": "tool", "content": "obs", "name": "t"}],
            "draft",
            schema_text="{}",
            purpose="p",
        )
    assert out == {"overall_score": 80}


@pytest.mark.asyncio
async def test_repair_json_non_dict_returns_none() -> None:
    llm = _llm_empty()
    llm.chat_json = AsyncMock(return_value=["not-a-dict"])
    with patch(
        "realmock.domains.records.agents.report.finalize.compress_text_blob",
        new=AsyncMock(return_value="compressed"),
    ):
        assert (
            await repair_json(
                llm,
                [{"role": "tool", "content": "obs", "name": "t"}],
                "draft",
                schema_text="{}",
                purpose="p",
            )
            is None
        )


@pytest.mark.asyncio
async def test_repair_json_exception_returns_none() -> None:
    llm = _llm_empty()
    llm.chat_json = AsyncMock(side_effect=RuntimeError("llm down"))
    with patch(
        "realmock.domains.records.agents.report.finalize.compress_text_blob",
        new=AsyncMock(return_value="compressed"),
    ):
        assert (
            await repair_json(
                llm,
                [{"role": "tool", "content": "obs", "name": "t"}],
                "draft",
                schema_text="{}",
                purpose="p",
            )
            is None
        )


@pytest.mark.asyncio
async def test_finalize_json_direct_payload() -> None:
    llm = _llm_empty()
    loop = SimpleNamespace(final_content='{"a": 1}', messages=[])
    assert await finalize_json(llm, loop, schema_text="{}", purpose="p") == {"a": 1}


@pytest.mark.asyncio
async def test_finalize_json_repairs_when_not_json() -> None:
    llm = _llm_empty()
    loop = SimpleNamespace(final_content="not json", messages=[{"role": "tool", "content": "o"}])
    with patch(
        "realmock.domains.records.agents.report.finalize.repair_json",
        new=AsyncMock(return_value={"fixed": True}),
    ) as rep:
        out = await finalize_json(llm, loop, schema_text="{}", purpose="turn notes")
        assert out == {"fixed": True}
        rep.assert_awaited_once()


# ---- synthesis ----










# ---- turn notes ----












