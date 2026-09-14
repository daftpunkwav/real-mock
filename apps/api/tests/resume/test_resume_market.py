"""Market role inference and template search queries."""

from __future__ import annotations

from realmock.domains.resume.services.analysis_market import (
    default_market_queries,
    generate_market_queries,
    infer_resume_query_locale,
    infer_search_keywords,
    infer_target_role_from_resume,
    market_query_planning_instruction,
)
from realmock.domains.resume.services.sites import RESUME_MARKET_SEARCH_SITES
from realmock.platform.models import Resume


def test_infer_target_role_from_skills_and_filename() -> None:
    with_skills = Resume(
        filename="x.pdf",
        file_type="pdf",
        raw_text="",
        parsed_profile='{"skills": ["Python", "FastAPI"]}',
    )
    role = infer_target_role_from_resume(with_skills)
    assert "Python" in role

    from_name = Resume(
        filename="backend_engineer.pdf",
        file_type="pdf",
        raw_text="",
        parsed_profile="{}",
    )
    assert "backend" in infer_target_role_from_resume(from_name).lower()


def test_infer_target_role_has_no_canned_fallback() -> None:
    empty = Resume(filename=".pdf", file_type="pdf", raw_text="", parsed_profile="{}")
    assert infer_target_role_from_resume(empty) == ""
    assert infer_search_keywords(empty) == []
    assert default_market_queries(empty) == []


def test_keyword_fallback_uses_resume_tokens_not_software_engineer() -> None:
    row = Resume(
        filename="cv.pdf",
        file_type="pdf",
        raw_text="Marketplace growth owner. SQL, Tableau, A/B testing.",
        parsed_profile="{}",
    )
    keywords = infer_search_keywords(row)
    assert keywords
    joined = " ".join(keywords).lower()
    assert "software engineer" not in joined
    assert "软件工程师" not in joined


def test_default_market_queries_include_role() -> None:
    row = Resume(
        filename="cv.pdf",
        file_type="pdf",
        raw_text="",
        parsed_profile='{"summary": "Java backend"}',
    )
    queries = default_market_queries(row)
    assert queries
    assert all("Java" in q or "backend" in q for q in queries)


def test_default_market_queries_follow_resume_language() -> None:
    zh = Resume(
        filename="cv.pdf",
        file_type="pdf",
        raw_text="熟悉 Python 与 FastAPI，曾负责招聘系统后端与面试流程。",
        parsed_profile='{"summary": "后端工程师"}',
    )
    assert infer_resume_query_locale(zh) == "zh-CN"
    zh_queries = default_market_queries(zh)
    assert any("招聘" in q for q in zh_queries)

    en = Resume(
        filename="cv.pdf",
        file_type="pdf",
        raw_text="Senior software engineer with eight years building Python backends.",
        parsed_profile='{"summary": "Backend engineer"}',
    )
    assert infer_resume_query_locale(en) == "en"
    en_queries = default_market_queries(en)
    assert any("job requirements" in q for q in en_queries)
    assert not any("招聘" in q for q in en_queries)


def test_market_query_planning_instruction_matches_locale() -> None:
    assert "Chinese search queries" in market_query_planning_instruction("zh-CN")
    assert "English search queries" in market_query_planning_instruction("en")
    assert "software engineer" in market_query_planning_instruction("en")
    assert "软件工程师" in market_query_planning_instruction("zh-CN")


async def test_generate_market_queries_prompt_follows_resume_language() -> None:
    captured: list[str] = []

    class _FakeLLM:
        async def chat_json(self, messages, temperature=0.2):
            captured.append(str(messages[1]["content"]))
            return {"queries": ["backend interview questions"]}

    zh = Resume(
        filename="cv.pdf",
        file_type="pdf",
        raw_text="熟悉 Python 与 FastAPI，曾负责招聘系统后端，主导性能优化与面试流程。",
        parsed_profile="{}",
    )
    queries, customized = await generate_market_queries(zh, _FakeLLM())  # type: ignore[arg-type]
    assert customized is True
    assert queries == ["backend interview questions"]
    assert "Chinese search queries" in captured[0]

    captured.clear()
    en = Resume(
        filename="cv.pdf",
        file_type="pdf",
        raw_text="Senior software engineer with eight years building distributed Python backends.",
        parsed_profile="{}",
    )
    await generate_market_queries(en, _FakeLLM())  # type: ignore[arg-type]
    assert "English search queries" in captured[0]


def test_market_sites_include_job_boards() -> None:
    assert "nowcoder.com" in RESUME_MARKET_SEARCH_SITES
    assert "zhipin.com" in RESUME_MARKET_SEARCH_SITES
    assert "linkedin.com" in RESUME_MARKET_SEARCH_SITES
    assert "levels.fyi" in RESUME_MARKET_SEARCH_SITES
    assert len(RESUME_MARKET_SEARCH_SITES) >= 8
