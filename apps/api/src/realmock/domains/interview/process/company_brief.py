"""Setup-page company brief: agent-researched question style / focus areas / process.

The interview-setup preview shows what a target company actually asks; instead of
hard-coded catalog copy, a bounded web-research agent produces a brief and the
result is cached per company + role + level + interview type + language
(``company_briefs``). Clearing the cache (settings page) forces regeneration on
the next request. Failure is honest and cheap: generation problems surface as an
error state in the UI, never as invented content.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import weakref
from typing import Any

from sqlalchemy.orm import Session

from realmock.domains.interview.models import CompanyBrief
from realmock.domains.interview.process.company_research import (
    STANDALONE_FETCH_BUDGET,
    STANDALONE_MAX_SECONDS,
    STANDALONE_SEARCH_BUDGET,
    run_web_research,
)
from realmock.platform.capabilities.ai.llm.json_extract import extract_json_object

logger = logging.getLogger(__name__)

#: After a failed generation the key fails fast for this long, so a retry
#: storm (user clicking retry, or a flapping network) cannot keep burning
#: LLM calls that each cost tens of seconds and web-tool budget.
FAILURE_COOLDOWN_SECONDS = 30.0
_MAX_TRACKED_FAILURES = 128

#: Singleflight: one in-flight generation per cache key; concurrent requesters
#: wait on the same lock and then hit the freshly written cache row. Weak
#: values let finished locks be garbage-collected without manual bookkeeping.
_generation_locks: "weakref.WeakValueDictionary[str, asyncio.Lock]" = (
    weakref.WeakValueDictionary()
)
_recent_failures: dict[str, float] = {}


def _remember_failure(key: str) -> None:
    now = time.monotonic()
    _recent_failures[key] = now
    for stale in [k for k, ts in _recent_failures.items() if now - ts >= FAILURE_COOLDOWN_SECONDS]:
        del _recent_failures[stale]
    while len(_recent_failures) > _MAX_TRACKED_FAILURES:
        _recent_failures.pop(next(iter(_recent_failures)))


def _cooled_down(key: str, now: float) -> bool:
    failed_at = _recent_failures.get(key)
    return failed_at is not None and now - failed_at < FAILURE_COOLDOWN_SECONDS


BRIEF_JSON_CONTRACT = """{
  "style": "<this company's interview question style, one short paragraph>",
  "focus_areas": ["<focus area>", "..."],
  "process": "<typical interview flow: rounds and what each round covers, one short paragraph>"
}"""

_BRIEF_SYSTEM = """You are a hiring-research analyst preparing a mock-interview brief.

Research the TARGET COMPANY's interview process for the given role, level and
interview type, then fill the JSON contract: question style, the focus areas
candidates should prepare, and the typical interview flow (rounds and their
coverage).

Tools:
- web_search: find sources (careers pages, interview-experience posts, hiring guides).
- web_fetch: read ONE page when the search snippets are not enough.

Hard rules:
1. Stay within the call budgets; when a tool reports budget exhaustion, stop researching.
2. If web_search returns SEARCH_UNAVAILABLE, stop researching immediately and answer from
   general knowledge — never invent sources or URLs.
3. Write search queries in the company's local language when obvious (e.g. a Chinese
   company → Chinese queries). Write the brief in the UI locale's language.
4. Never invent facts; keep every claim grounded in what you found or general knowledge.
5. Finish with exactly ONE JSON object matching this contract (no markdown fences):
{contract}"""


def _normalize(name: str) -> str:
    return "".join((name or "").strip().lower().split())


def _scope_digest(role: str, level: str, interview_type: str, lang: str) -> str:
    scope = "|".join(
        (
            _normalize(role),
            _normalize(level),
            _normalize(interview_type),
            (lang or "").strip() or "en",
        )
    )
    return hashlib.sha1(scope.encode("utf-8")).hexdigest()[:10]


def company_cache_key(
    company: str,
    lang: str,
    role: str = "",
    level: str = "",
    interview_type: str = "",
) -> str:
    """Cache identity: normalized company + digest of role / level / interview type / language."""
    return f"{_normalize(company)}:{_scope_digest(role, level, interview_type, lang)}"


def get_cached_brief(
    db: Session,
    company: str,
    lang: str,
    role: str = "",
    level: str = "",
    interview_type: str = "",
) -> CompanyBrief | None:
    return (
        db.query(CompanyBrief)
        .filter(
            CompanyBrief.company_key
            == company_cache_key(company, lang, role=role, level=level, interview_type=interview_type)
        )
        .first()
    )


def _parse_focus(raw: str) -> list[str]:
    try:
        data = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(item).strip() for item in data if str(item).strip()][:8]


def clear_company_briefs(db: Session) -> int:
    """Drop the whole brief cache including in-memory failure cooldowns.

    The settings-page action promises regeneration on the next request, so a
    key that just failed must not stay cooled down after the clear.
    """
    count = db.query(CompanyBrief).count()
    db.query(CompanyBrief).delete(synchronize_session=False)
    db.commit()
    _recent_failures.clear()
    return count


async def generate_company_brief(
    llm: Any,  # noqa: ANN401 - LLMClient duck type
    *,
    company: str,
    role: str,
    level: str,
    interview_type: str,
    locale: str,
) -> dict[str, Any] | None:
    """Research one company and return ``{style, focus_areas, process}`` (or None)."""
    name = (company or "").strip()
    if not name:
        return None
    system = _BRIEF_SYSTEM.format(contract=BRIEF_JSON_CONTRACT)
    user = (
        f"Target company: {name}\n"
        f"Target role: {role or 'unknown'}\n"
        f"Level: {level or 'unknown'}\n"
        f"Interview type: {interview_type or 'unknown'}\n"
        f"UI locale (write the brief in this language): {locale or 'unknown'}\n\n"
        "Research this company's interviews now, focused on this role, level and interview "
        "type. Finish with the JSON object only."
    )
    final = await run_web_research(
        llm,
        system=system,
        user=user,
        search_budget=STANDALONE_SEARCH_BUDGET,
        fetch_budget=STANDALONE_FETCH_BUDGET,
        max_seconds=STANDALONE_MAX_SECONDS,
    )
    if final is None:
        return None
    payload = extract_json_object(final)
    if not isinstance(payload, dict):
        logger.info("company brief output unusable company=%s (len=%s)", name, len(final))
        return None
    style = str(payload.get("style") or "").strip()
    process_text = str(payload.get("process") or "").strip()
    focus_areas = payload.get("focus_areas")
    if not style and not process_text:
        logger.info("company brief empty company=%s", name)
        return None
    return {
        "style": style,
        "focus_areas": [str(a).strip() for a in focus_areas if str(a).strip()][:8]
        if isinstance(focus_areas, list)
        else [],
        "process": process_text,
    }


async def get_or_create_brief(
    db: Session,
    llm: Any,  # noqa: ANN401 - LLMClient duck type
    *,
    company: str,
    role: str,
    level: str,
    interview_type: str = "",
    locale: str,
) -> dict[str, Any] | None:
    """Cached brief lookup + generation fallback; persists fresh results.

    Robustness contract: a generation is a full agent run (LLM + web tools),
    so identical concurrent requests share ONE generation (singleflight — the
    waiter re-checks the cache inside the lock), a failed key fails fast for
    ``FAILURE_COOLDOWN_SECONDS`` instead of re-burning the LLM on every retry,
    and a cache-write failure only loses the caching, never the answer.
    """
    key = company_cache_key(
        company, locale, role=role, level=level, interview_type=interview_type
    )
    lock = _generation_locks.setdefault(key, asyncio.Lock())
    async with lock:
        cached = get_cached_brief(
            db, company, locale, role=role, level=level, interview_type=interview_type
        )
        if cached is not None:
            return {
                "company": cached.company_name or company,
                "style": cached.style or "",
                "focus_areas": _parse_focus(cached.focus_areas),
                "process": cached.process or "",
                "cached": True,
            }
        if _cooled_down(key, time.monotonic()):
            return None
        brief = await generate_company_brief(
            llm,
            company=company,
            role=role,
            level=level,
            interview_type=interview_type,
            locale=locale,
        )
        if brief is None:
            _remember_failure(key)
            return None
        try:
            row = CompanyBrief(
                company_key=key,
                company_name=company.strip(),
                lang=(locale or "").strip() or "en",
                style=brief["style"],
                focus_areas=json.dumps(brief["focus_areas"], ensure_ascii=False),
                process=brief["process"],
            )
            db.merge(row)
            db.commit()
        except Exception as exc:  # noqa: BLE001 - cache write must not sink the result
            db.rollback()
            logger.warning("company brief cache write failed key=%s: %s", key, exc)
        return {**brief, "company": company.strip(), "cached": False}


__all__ = [
    "BRIEF_JSON_CONTRACT",
    "clear_company_briefs",
    "company_cache_key",
    "generate_company_brief",
    "get_cached_brief",
    "get_or_create_brief",
]
