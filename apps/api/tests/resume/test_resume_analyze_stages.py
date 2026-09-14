"""Resume deep-review orchestration: Agent loop persist, score, slots, locale.

Contract:
- Agent returns one evaluation JSON payload; the platform normalizes and persists;
- Overall score is the equal-weight mean of dimension scores when present;
- Concurrency cap from the catalog: A1007 when slots are full.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from realmock.domains.resume.services import analysis as analysis_module
from realmock.domains.resume.services import analyze_slots
from realmock.domains.resume.services.analysis import analyze_resume_with_llm
from realmock.domains.resume.services.analysis_prompt import get_review_agent_prompt
from realmock.platform.core.errors import ApiBusinessError
from realmock.platform.models import Resume


@pytest.fixture(autouse=True)
def _fresh_upload_settings():
    from realmock.platform.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _reset_analyze_slots():
    analyze_slots.reset_slots_for_tests()
    yield
    analyze_slots.reset_slots_for_tests()


def _stub_llm(monkeypatch: pytest.MonkeyPatch) -> object:
    class _Stub:
        api_key = "k"
        supports_vision = False
        context_window = 0
        max_tokens = 0

        @classmethod
        def from_db(cls, db, **kw):
            return cls()

    monkeypatch.setattr(analysis_module, "LLMClient", _Stub)
    return _Stub()


def _payload(**overrides: object) -> dict:
    data = {
        "content_review": "Content is acceptable",
        "red_flags": ["Buzzword stuffing"],
        "market_insights": ["Market observation A"],
        "salary_positioning": "Internship 300-450/day",
        "project_deep_dive": ["Deep-dive point: which module contains the core logic"],
        "repo_verification": [
            {"repo": "me/real-mock", "verdict": "Description matches", "details": "Active commits"}
        ],
        "repo_evidence": [
            {"repo": "me/real-mock", "stars": 5, "url": "https://github.com/me/real-mock"}
        ],
        "score": 78,
        "headline": "Test persona definition",
        "strengths": ["Project A has metrics"],
        "search_queries_used": ["q1", "q2"],
    }
    data.update(overrides)
    return data


def test_analyze_runs_agent_and_persists(api_db, monkeypatch: pytest.MonkeyPatch) -> None:
    """Agent payload is normalized, scored, and written to the resume row."""
    _stub_llm(monkeypatch)

    async def fake_review(resume, db, llm, *, locale="zh-CN", on_event=None):
        del resume, db, llm, locale, on_event
        return _payload()

    monkeypatch.setattr(analysis_module, "run_resume_review", fake_review)

    row = Resume(filename="a.pdf", file_type="pdf", raw_text="Main text content", parsed_profile="{}")
    api_db.add(row)
    api_db.commit()
    api_db.refresh(row)

    analysis = asyncio.run(analyze_resume_with_llm(row, api_db))
    assert analysis.score == 78
    assert analysis.content_review == "Content is acceptable"
    assert analysis.market_insights == ["Market observation A"]
    assert analysis.project_deep_dive == ["Deep-dive point: which module contains the core logic"]
    assert analysis.repo_verification[0].verdict == "Description matches"
    assert analysis.search_queries_used == ["q1", "q2"]
    assert analysis.repo_evidence[0].repo == "me/real-mock"

    api_db.refresh(row)
    persisted = json.loads(row.analysis)
    assert persisted["score"] == 78
    assert persisted["content_review"] == "Content is acceptable"
    assert persisted["repo_evidence"][0]["repo"] == "me/real-mock"
    assert row.score == 78


def test_analyze_without_github_evidence_succeeds(api_db, monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-engineering resumes can omit GitHub fields entirely."""
    _stub_llm(monkeypatch)

    async def fake_review(resume, db, llm, *, locale="zh-CN", on_event=None):
        del resume, db, llm, locale, on_event
        return _payload(
            repo_evidence=[],
            repo_verification=[],
            project_deep_dive=[],
            search_queries_used=["product manager JD 关键词"],
        )

    monkeypatch.setattr(analysis_module, "run_resume_review", fake_review)
    row = Resume(
        filename="pm.pdf",
        file_type="pdf",
        raw_text="Product manager with marketplace growth work.",
        parsed_profile='{"target_role": "Product Manager"}',
    )
    api_db.add(row)
    api_db.commit()
    api_db.refresh(row)
    analysis = asyncio.run(analyze_resume_with_llm(row, api_db))
    assert analysis.repo_evidence == []
    assert analysis.search_queries_used == ["product manager JD 关键词"]


def test_score_is_deterministic_mean_of_dims(api_db, monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the aggregate score deterministic: equal-weight mean of dimension scores."""
    dims = {f"dim{i}": {"score": 50 + (i % 5) * 10, "comment": f"c{i}"} for i in range(12)}
    _stub_llm(monkeypatch)

    async def fake_review(resume, db, llm, *, locale="zh-CN", on_event=None):
        del resume, db, llm, locale, on_event
        return _payload(score=99, dimension_scores=dims, headline="h")

    monkeypatch.setattr(analysis_module, "run_resume_review", fake_review)
    row = Resume(filename="dims.pdf", file_type="pdf", raw_text="Dimension main text", parsed_profile="{}")
    api_db.add(row)
    api_db.commit()
    api_db.refresh(row)

    analysis = asyncio.run(analyze_resume_with_llm(row, api_db))
    expected = round(sum(50 + (i % 5) * 10 for i in range(12)) / 12)
    assert analysis.score == expected
    from realmock.domains.resume.services.analysis_normalize import (
        benchmark_percentile_from_score,
    )

    assert analysis.benchmark_percentile == benchmark_percentile_from_score(expected)
    api_db.refresh(row)
    assert row.score == expected


def test_invalid_agent_json_raises_c0002(api_db, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_llm(monkeypatch)

    async def fake_review(resume, db, llm, *, locale="zh-CN", on_event=None):
        del resume, db, llm, locale, on_event
        from realmock.platform.core.errors import raise_error

        raise_error("C0002")

    monkeypatch.setattr(analysis_module, "run_resume_review", fake_review)
    row = Resume(filename="c.pdf", file_type="pdf", raw_text="Main text C", parsed_profile="{}")
    api_db.add(row)
    api_db.commit()
    api_db.refresh(row)
    with pytest.raises(ApiBusinessError) as exc_info:
        asyncio.run(analyze_resume_with_llm(row, api_db))
    assert exc_info.value.error_code == "C0002"


def test_zero_score_without_dims_raises_c0002(api_db, monkeypatch: pytest.MonkeyPatch) -> None:
    """A long narrative with overall score 0 and no dimensions must not persist."""
    _stub_llm(monkeypatch)

    async def fake_review(resume, db, llm, *, locale="zh-CN", on_event=None):
        del resume, db, llm, locale, on_event
        return _payload(
            score=0,
            dimension_scores={},
            content_review="A" * 80,
            headline="Persona line that looks complete",
            first_impression="First impression text that looks complete",
        )

    monkeypatch.setattr(analysis_module, "run_resume_review", fake_review)
    row = Resume(filename="zero.pdf", file_type="pdf", raw_text="Main text content", parsed_profile="{}")
    api_db.add(row)
    api_db.commit()
    api_db.refresh(row)
    with pytest.raises(ApiBusinessError) as exc_info:
        asyncio.run(analyze_resume_with_llm(row, api_db))
    assert exc_info.value.error_code == "C0002"


def test_zero_score_recovers_from_chat_json(api_db, monkeypatch: pytest.MonkeyPatch) -> None:
    from realmock.domains.resume.schemas.limits import DIMENSION_KEYS

    class _RecoverStub:
        api_key = "k"
        supports_vision = False
        context_window = 0
        max_tokens = 0

        @classmethod
        def from_db(cls, db, **kw):
            return cls()

        async def chat_json(self, messages, **kwargs):
            del messages, kwargs
            keys = list(DIMENSION_KEYS)[:4]
            return {
                "score": 64,
                "dimension_scores": {key: {"score": 64, "comment": "ok"} for key in keys},
            }

    monkeypatch.setattr(analysis_module, "LLMClient", _RecoverStub)

    async def fake_review(resume, db, llm, *, locale="zh-CN", on_event=None):
        del resume, db, llm, locale, on_event
        return _payload(
            score=0,
            dimension_scores={},
            content_review="A" * 80,
            headline="Persona line that looks complete",
        )

    monkeypatch.setattr(analysis_module, "run_resume_review", fake_review)
    row = Resume(filename="recover.pdf", file_type="pdf", raw_text="Main text content", parsed_profile="{}")
    api_db.add(row)
    api_db.commit()
    api_db.refresh(row)
    analysis = asyncio.run(analyze_resume_with_llm(row, api_db))
    assert analysis.score == 64
    assert len(analysis.dimension_scores) >= 4


def test_score_only_recovery_raises_c0002(api_db, monkeypatch: pytest.MonkeyPatch) -> None:
    """Recovery that returns a total without dimension scores must not persist."""

    class _ScoreOnlyStub:
        api_key = "k"
        supports_vision = False
        context_window = 0
        max_tokens = 0

        @classmethod
        def from_db(cls, db, **kw):
            return cls()

        async def chat_json(self, messages, **kwargs):
            del messages, kwargs
            return {"score": 64}

    monkeypatch.setattr(analysis_module, "LLMClient", _ScoreOnlyStub)

    async def fake_review(resume, db, llm, *, locale="zh-CN", on_event=None):
        del resume, db, llm, locale, on_event
        return _payload(
            score=0,
            dimension_scores={},
            content_review="A" * 80,
            headline="Persona line that looks complete",
        )

    monkeypatch.setattr(analysis_module, "run_resume_review", fake_review)
    row = Resume(filename="score-only.pdf", file_type="pdf", raw_text="Main text content", parsed_profile="{}")
    api_db.add(row)
    api_db.commit()
    api_db.refresh(row)
    with pytest.raises(ApiBusinessError) as exc_info:
        asyncio.run(analyze_resume_with_llm(row, api_db))
    assert exc_info.value.error_code == "C0002"


def test_empty_agent_payload_raises_c0002(api_db, monkeypatch: pytest.MonkeyPatch) -> None:
    """A truncated/empty evaluation must not persist as a successful score-0 review."""
    _stub_llm(monkeypatch)

    async def fake_review(resume, db, llm, *, locale="zh-CN", on_event=None):
        del resume, db, llm, locale, on_event
        return {}

    monkeypatch.setattr(analysis_module, "run_resume_review", fake_review)
    row = Resume(filename="empty.pdf", file_type="pdf", raw_text="Main text", parsed_profile="{}")
    api_db.add(row)
    api_db.commit()
    api_db.refresh(row)
    with pytest.raises(ApiBusinessError) as exc_info:
        asyncio.run(analyze_resume_with_llm(row, api_db))
    assert exc_info.value.error_code == "C0002"


def test_agent_loop_failure_raises_c0001(api_db, monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_llm(monkeypatch)

    async def fake_review(resume, db, llm, *, locale="zh-CN", on_event=None):
        del resume, db, llm, locale, on_event
        raise RuntimeError("upstream down")

    monkeypatch.setattr(analysis_module, "run_resume_review", fake_review)
    row = Resume(filename="c.pdf", file_type="pdf", raw_text="Main text C", parsed_profile="{}")
    api_db.add(row)
    api_db.commit()
    api_db.refresh(row)
    with pytest.raises(ApiBusinessError) as exc_info:
        asyncio.run(analyze_resume_with_llm(row, api_db))
    assert exc_info.value.error_code == "C0001"


def test_analyze_uses_resume_language_not_ui_locale(api_db, monkeypatch: pytest.MonkeyPatch) -> None:
    """Plan / evaluation language follows the resume body, not the request locale."""
    _stub_llm(monkeypatch)
    seen: list[str] = []

    async def fake_review(resume, db, llm, *, locale="zh-CN", on_event=None):
        del resume, db, llm, on_event
        seen.append(locale)
        return _payload(score=50)

    monkeypatch.setattr(analysis_module, "run_resume_review", fake_review)

    chinese = Resume(
        filename="zh.pdf",
        file_type="pdf",
        raw_text="熟悉 Python 与 FastAPI，曾负责招聘系统后端，主导性能优化、接口设计和面试流程改进。",
        parsed_profile="{}",
    )
    english = Resume(
        filename="en.pdf",
        file_type="pdf",
        raw_text="Senior software engineer with eight years building distributed backends in Python and FastAPI.",
        parsed_profile="{}",
    )
    api_db.add_all([chinese, english])
    api_db.commit()
    api_db.refresh(chinese)
    api_db.refresh(english)

    asyncio.run(analyze_resume_with_llm(chinese, api_db, locale="en"))
    asyncio.run(analyze_resume_with_llm(english, api_db, locale="zh-CN"))
    assert seen == ["zh-CN", "en"]
    prompt = get_review_agent_prompt("en")
    assert "review_set_plan step titles in English" in prompt


def test_zero_overall_without_dims_raises_c0002(api_db, monkeypatch: pytest.MonkeyPatch) -> None:
    """Section scores must not silently become an overall score without dimensions."""
    _stub_llm(monkeypatch)

    async def fake_review(resume, db, llm, *, locale="zh-CN", on_event=None):
        del resume, db, llm, locale, on_event
        return _payload(
            score=0,
            dimension_scores={},
            content_review="A" * 80,
            section_reviews=[
                {"section": "projects", "score": 80, "verdict": "ok", "detail": "d"},
                {"section": "skills", "score": 60, "verdict": "ok", "detail": "d"},
            ],
        )

    monkeypatch.setattr(analysis_module, "run_resume_review", fake_review)
    row = Resume(filename="sections.pdf", file_type="pdf", raw_text="Main text content", parsed_profile="{}")
    api_db.add(row)
    api_db.commit()
    api_db.refresh(row)
    with pytest.raises(ApiBusinessError) as exc_info:
        asyncio.run(analyze_resume_with_llm(row, api_db))
    assert exc_info.value.error_code == "C0002"


def test_analyze_parallel_cap_three(monkeypatch: pytest.MonkeyPatch) -> None:
    """Concurrency cap: a new request gets A1007 when all slots are occupied."""

    async def scenario() -> list[object]:
        seen: list[object] = []
        for _ in range(analyze_slots.MAX_PARALLEL_ANALYZE):
            await analyze_slots.acquire_slot()
            seen.append("acquired")
        try:
            await analyze_slots.acquire_slot()
            seen.append("should-not-happen")
        except ApiBusinessError as e:
            seen.append(e.error_code)
        for _ in range(analyze_slots.MAX_PARALLEL_ANALYZE):
            await analyze_slots.release_slot()
        await analyze_slots.acquire_slot()
        await analyze_slots.release_slot()
        seen.append("reacquired")
        return seen

    expected = ["acquired"] * analyze_slots.MAX_PARALLEL_ANALYZE + ["A1007", "reacquired"]
    assert asyncio.run(scenario()) == expected


def test_commit_retry_yields_event_loop_during_backoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sqlalchemy.exc

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(analysis_module.asyncio, "sleep", fake_sleep)

    class _LockedTwiceDB:
        def __init__(self) -> None:
            self.n = 0

        def commit(self) -> None:
            self.n += 1
            if self.n < 3:
                raise sqlalchemy.exc.OperationalError(
                    "stmt", {}, Exception("database is locked")
                )

        def rollback(self) -> None:
            pass

    asyncio.run(analysis_module._commit_with_retry(_LockedTwiceDB()))
    assert sleeps == [1.5, 3.0]


def test_market_context_cached_per_resume(api_db, monkeypatch: pytest.MonkeyPatch) -> None:
    from realmock.domains.resume.services import analysis_market

    calls = {"n": 0}

    async def fake_queries(r, llm):
        calls["n"] += 1
        return ([f"q{calls['n']}"], True)

    async def fake_gather(r, queries):
        return (f"ctx-{queries[0]}", list(queries))

    monkeypatch.setattr(analysis_market, "generate_market_queries", fake_queries)
    monkeypatch.setattr(analysis_market, "gather_resume_market_context", fake_gather)

    async def run(r) -> tuple[str, list[str]]:
        return await analysis_market.get_market_context_cached(r, llm=None)

    row_a = Resume(filename="a.pdf", file_type="pdf", raw_text="Resume A", parsed_profile="{}")
    row_a2 = Resume(filename="a-again.pdf", file_type="pdf", raw_text="Resume A", parsed_profile="{}")
    row_b = Resume(filename="b.pdf", file_type="pdf", raw_text="Resume B", parsed_profile="{}")

    ctx1, q1 = asyncio.run(run(row_a))
    ctx2, q2 = asyncio.run(run(row_a2))
    ctx3, q3 = asyncio.run(run(row_b))

    assert calls["n"] == 2
    assert ctx1 == ctx2 and q1 == q2
    assert ctx3 != ctx1


def test_extract_github_repos_dedup_and_cap() -> None:
    from realmock.domains.resume.services.repo_evidence import extract_github_repos

    text = (
        "Projects https://github.com/me/real-mock and https://github.com/me/real-mock.git "
        "and https://github.com/other/proj. Verify deduplication and truncation."
    )
    repos = extract_github_repos(text, limit=3)
    assert [(t.owner, t.repo) for t in repos] == [("me", "real-mock"), ("other", "proj")]
