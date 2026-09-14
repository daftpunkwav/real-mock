"""Market query planning: template fallback plus an LLM planner.

Responsibilities:
- Build template queries from inferred keywords in the resume's language
- Optionally tailor queries with an LLM planner (template fallback on failure)

Never invent a canned job title such as "software engineer". When the target
role is missing, search by skills and project keywords instead. Query caps
live in ``schemas.limits``. Must not import FastAPI or ORM sessions.
"""

from __future__ import annotations

import asyncio
import logging

from realmock.domains.resume.schemas.limits import MAX_SEARCH_QUERIES
from realmock.domains.resume.services.market_keywords import (
    infer_resume_query_locale,
    infer_search_keywords,
)
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.models import Resume

logger = logging.getLogger(__name__)

_ZH_QUERY_TEMPLATES = (
    "{role} 招聘要求 技术栈 面试",
    "{role} JD 关键技能 关键词",
)
_EN_QUERY_TEMPLATES = (
    "{role} job requirements tech stack interview",
    "{role} job description key skills keywords",
)


def default_market_queries(r: Resume) -> list[str]:
    """Template queries from inferred keywords. Empty when no keywords exist."""
    keywords = infer_search_keywords(r)
    if not keywords:
        return []
    role = " ".join(keywords[:4])
    templates = (
        _ZH_QUERY_TEMPLATES if infer_resume_query_locale(r) == "zh-CN" else _EN_QUERY_TEMPLATES
    )
    return [template.format(role=role) for template in templates]


def market_query_planning_instruction(locale: str) -> str:
    """User-prompt instruction: search queries must match the resume language."""
    if locale == "en":
        return (
            "Provide 2~3 English search queries to retrieve real hiring requirements "
            "for the candidate’s target role, high-frequency skill keywords, and interview topics. "
            "Each query at most 24 words. If no target role is stated, search by skills and "
            "project keywords from this resume — never invent a generic title such as "
            "software engineer. Tailor to the English-speaking job market rather than "
            "reciting the resume."
        )
    return (
        "Provide 2~3 Chinese search queries to retrieve real hiring requirements "
        "for the candidate’s target role, high-frequency skill keywords, and interview topics. "
        "Each query at most 24 characters. If no target role is stated, search by skills and "
        "project keywords from this resume — never invent a generic title such as "
        "软件工程师. Tailor to the Chinese job market rather than reciting the resume."
    )


async def generate_market_queries(r: Resume, llm: LLMClient) -> tuple[list[str], bool]:
    """Optional planner: tailor search terms. Falls back to keyword templates.

    Returns ``(queries, is_customized)``. Query language follows the resume text.
    """
    fallback = default_market_queries(r)
    profile_hint = (r.parsed_profile or "")[:1500]
    raw_hint = (r.raw_text or "")[:2500]
    if not profile_hint and not raw_hint:
        return fallback, False
    locale = infer_resume_query_locale(r)
    instruction = market_query_planning_instruction(locale)
    messages = [
        {
            "role": "system",
            "content": "You are the search planning assistant for the recruitment market. Only output JSON: {\"queries\": [\"...\"]}",
        },
        {
            "role": "user",
            "content": (
                "Resume parsing file:\n"
                f"{profile_hint}\n\nExcerpts from the original resume:\n{raw_hint}\n\n"
                f"{instruction}"
            ),
        },
    ]
    try:
        data = await asyncio.wait_for(
            llm.chat_json(messages, temperature=0.2), timeout=25.0
        )
        raw = data.get("queries") if isinstance(data, dict) else None
        if isinstance(raw, list):
            cleaned = [str(q).strip()[:40] for q in raw if str(q).strip()][:MAX_SEARCH_QUERIES]
            if cleaned:
                return cleaned, True
    except Exception as e:
        logger.info("Customized search word generation failed, fallback keyword queries: %s", e)
    return fallback, False


__all__ = [
    "default_market_queries",
    "generate_market_queries",
    "market_query_planning_instruction",
]
