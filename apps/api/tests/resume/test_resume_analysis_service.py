"""Analysis service tests for src/realmock/domains/resume/services/analysis.py.

Covers: _commit_with_retry locked/non-locked branches, _request_score_repair
no-client/exception/non-dict branches, _recover_incomplete_scores C0002 paths,
analyze_resume_with_llm missing-key/missing-file/agent-crash/db-write branches.
Conventions: no real network/model downloads (all clients mocked); faked LLM/DB;
rate limits reset per test.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import sqlalchemy.exc

import realmock.domains.resume.services.analysis as amod
from realmock.domains.resume.schemas.analysis import ResumeAnalysis
from realmock.platform.core.errors import ApiBusinessError
from realmock.platform.models import Resume


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()


def _resume(**over) -> Resume:
    base = {"filename": "a.pdf", "file_type": "pdf", "raw_text": "body", "parsed_profile": "{}"}
    base.update(over)
    return Resume(**base)


def _analysis(**over) -> ResumeAnalysis:
    base = {
        "score": 0,
        "headline": "h",
        "first_impression": "f",
        "overall_narrative": "n" * 200,
        "content_review": "c" * 200,
        "layout_review": "l",
        "typography_review": "t",
        "strengths": [],
        "weaknesses": [],
        "dimension_scores": {},
    }
    base.update(over)
    return ResumeAnalysis.model_validate(base)


@pytest.mark.asyncio
async def test_commit_non_locked_raises_immediately() -> None:
    db = MagicMock()
    db.commit.side_effect = sqlalchemy.exc.OperationalError("s", {}, Exception("disk i/o error"))
    with pytest.raises(sqlalchemy.exc.OperationalError):
        await amod._commit_with_retry(db)
    assert db.rollback.called


@pytest.mark.asyncio
async def test_commit_locked_on_last_attempt_raises(monkeypatch) -> None:
    async def _no_sleep(s):
        return None

    monkeypatch.setattr(amod.asyncio, "sleep", _no_sleep)
    db = MagicMock()
    db.commit.side_effect = sqlalchemy.exc.OperationalError("s", {}, Exception("database is locked"))
    with pytest.raises(sqlalchemy.exc.OperationalError):
        await amod._commit_with_retry(db)
    assert db.commit.call_count == amod.COMMIT_RETRY_ATTEMPTS


@pytest.mark.asyncio
async def test_request_repair_no_chat_json() -> None:
    out = await amod._request_score_repair(SimpleNamespace(), _analysis(), locale="en")
    assert out is None


@pytest.mark.asyncio
async def test_request_repair_exception_returns_none() -> None:
    llm = SimpleNamespace(chat_json=AsyncMock(side_effect=RuntimeError("llm down")))
    out = await amod._request_score_repair(llm, _analysis(), locale="en")
    assert out is None


@pytest.mark.asyncio
async def test_request_repair_non_dict_returns_none() -> None:
    llm = SimpleNamespace(chat_json=AsyncMock(return_value=["not-a-dict"]))
    out = await amod._request_score_repair(llm, _analysis(), locale="en")
    assert out is None


@pytest.mark.asyncio
async def test_recover_not_dict_raises_c0002(monkeypatch) -> None:
    monkeypatch.setattr(amod, "_request_score_repair", AsyncMock(return_value=None))
    with pytest.raises(ApiBusinessError) as e:
        await amod._recover_incomplete_scores(SimpleNamespace(), _analysis(), locale="en")
    assert e.value.error_code == "C0002"


@pytest.mark.asyncio
async def test_recover_generic_validation_error_raises_c0002(monkeypatch) -> None:
    monkeypatch.setattr(
        amod, "_request_score_repair", AsyncMock(return_value={"score": 80, "dimension_scores": {}})
    )

    def _boom(payload, *, locale):
        raise ValueError("bad shape")

    monkeypatch.setattr(amod, "_to_resume_analysis", _boom)
    with pytest.raises(ApiBusinessError) as e:
        await amod._recover_incomplete_scores(SimpleNamespace(), _analysis(), locale="en")
    assert e.value.error_code == "C0002"


@pytest.mark.asyncio
async def test_analyze_no_api_key_raises_a0006(monkeypatch) -> None:
    class _LLM:
        api_key = ""

        @classmethod
        def from_db(cls, db, **k):
            return cls()

    monkeypatch.setattr(amod, "LLMClient", _LLM)
    with pytest.raises(ApiBusinessError) as e:
        await amod.analyze_resume_with_llm(_resume(), MagicMock())
    assert e.value.error_code == "A0006"


@pytest.mark.asyncio
async def test_analyze_missing_file_raises_a1004(monkeypatch) -> None:
    class _LLM:
        api_key = "k"

        @classmethod
        def from_db(cls, db, **k):
            return cls()

    monkeypatch.setattr(amod, "LLMClient", _LLM)
    monkeypatch.setattr(amod, "find_resume_file", lambda r: None)
    with pytest.raises(ApiBusinessError) as e:
        await amod.analyze_resume_with_llm(_resume(raw_text="   "), MagicMock())
    assert e.value.error_code == "A1004"


@pytest.mark.asyncio
async def test_analyze_agent_crash_raises_c0001(monkeypatch) -> None:
    class _LLM:
        api_key = "k"

        @classmethod
        def from_db(cls, db, **k):
            return cls()

    monkeypatch.setattr(amod, "LLMClient", _LLM)
    monkeypatch.setattr(amod, "run_resume_review", AsyncMock(side_effect=RuntimeError("agent down")))
    with pytest.raises(ApiBusinessError) as e:
        await amod.analyze_resume_with_llm(_resume(raw_text="body"), MagicMock())
    assert e.value.error_code == "C0001"


@pytest.mark.asyncio
async def test_analyze_db_write_fail_raises_b1001(monkeypatch, api_db) -> None:
    class _LLM:
        api_key = "k"

        @classmethod
        def from_db(cls, db, **k):
            return cls()

    monkeypatch.setattr(amod, "LLMClient", _LLM)

    async def _fake_review(r, db, llm, *, locale="zh-CN", on_event=None):
        return {
            "content_review": "c" * 300,
            "layout_review": "l" * 100,
            "typography_review": "t" * 100,
            "overall_narrative": "n" * 300,
            "headline": "h",
            "first_impression": "f",
            "score": 80,
            "dimension_scores": {},
        }

    monkeypatch.setattr(amod, "run_resume_review", _fake_review)
    row = Resume(filename="a.pdf", file_type="pdf", raw_text="body-text", parsed_profile="{}")
    api_db.add(row)
    api_db.commit()
    api_db.refresh(row)
    monkeypatch.setattr(amod, "_commit_with_retry", AsyncMock(side_effect=RuntimeError("db down")))
    with pytest.raises(ApiBusinessError) as e:
        await amod.analyze_resume_with_llm(row, api_db)
    assert e.value.error_code == "B1001"
