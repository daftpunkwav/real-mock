"""Target-company web research for the interview planning pipeline.

Companies absent from the built-in catalog (user-typed custom names) have no
interview-style context, so a bounded researcher agent runs once with the
platform ``web_search`` / ``web_fetch`` tools and emits a compact digest: the
company's interview process, round structure (how many technical vs HR rounds),
and question-style preferences. The digest is persisted on the process/session
row and reused by the round planner, the flow planner, and the interviewer
opening prompt — research runs once per process, never per turn.

Failure is honest and cheap: any timeout, exhausted budget, or unparseable
output returns ``None`` and callers proceed with catalog context only.
Planning must never block an interview.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy.orm import Session

from realmock.domains.interview.models import InterviewProcess, InterviewSession
from realmock.platform.capabilities.ai.agent import run_agent_loop
from realmock.platform.capabilities.ai.agent.tools import (
    ToolBundle,
    invoke_with_timeout,
    search_tool_spec,
    web_fetch_tool_spec,
)
from realmock.platform.capabilities.ai.llm.json_extract import extract_json_object
from realmock.platform.catalogs.company import get_company_by_id

logger = logging.getLogger(__name__)

#: Per-research web budgets; exhaustion speaks the tools' own failure markers.
RESEARCH_SEARCH_BUDGET = 3
RESEARCH_FETCH_BUDGET = 2
#: Standalone sessions research inline before the opening turn, so their
#: budget is tighter than the process-level (round-planner) budget.
STANDALONE_SEARCH_BUDGET = 2
STANDALONE_FETCH_BUDGET = 1
STANDALONE_MAX_SECONDS = 45.0
PROCESS_MAX_SECONDS = 75.0
RESEARCH_TOOL_TIMEOUT_SECONDS = 15.0
RESEARCH_MAX_ROUNDS = 6

#: Persisted digests are capped so prompt sections stay bounded.
DIGEST_MAX_CHARS = 2000

_WEB_BUDGET_MARKERS = {
    "web_search": "SEARCH_UNAVAILABLE",
    "web_fetch": "FETCH_FAILED",
}

RESEARCH_JSON_CONTRACT = """{
  "process": "<known interview flow / stages, one paragraph>",
  "rounds": "<round structure: how many rounds, how many technical vs HR vs management>",
  "focus": "<what the company focuses on and its question style>",
  "notes": "<anything else useful for interviewing a candidate here>",
  "sources": ["<url>", ...],
  "confidence": "<high|medium|low>"
}"""

_RESEARCH_SYSTEM = """You are a hiring-research analyst preparing context for a mock-interview planner.

Research the TARGET COMPANY's interview process for the given role and level:
typical stages, number of rounds (how many technical vs HR rounds), interview
style, focus areas, and well-known question patterns.

Tools:
- web_search: find sources (careers pages, interview-experience posts, hiring guides).
- web_fetch: read ONE page when the search snippets are not enough.

Hard rules:
1. Stay within the call budgets; when a tool reports budget exhaustion, stop researching.
2. If web_search returns SEARCH_UNAVAILABLE, stop researching immediately and answer from
   general knowledge with confidence "low" — never invent sources or URLs.
3. Write search queries in the company's local language when obvious (e.g. a Chinese
   company → Chinese queries).
4. Never invent facts; anything unknown stays "unknown".
5. Finish with exactly ONE JSON object matching this contract (no markdown fences):
{contract}"""


def needs_company_research(company: str) -> bool:
    """True when ``company`` is not in the built-in catalog (custom name)."""
    name = (company or "").strip()
    return bool(name) and get_company_by_id(name) is None


def blend_company_context(catalog_context: str, digest: str) -> str:
    """Company context for prompts: research digest wins, catalog is the fallback.

    Custom companies never have catalog data (only a generic line), so a digest
    fully replaces it; preset companies have no digest and keep the catalog.
    """
    digest = (digest or "").strip()
    return digest if digest else (catalog_context or "")


def load_session_company_research(db: Session, session: InterviewSession) -> str:
    """Research digest for a session: its own (standalone) or its process's."""
    own = (getattr(session, "company_research", "") or "").strip()
    if own:
        return own
    process_id = getattr(session, "process_id", None)
    if not process_id:
        return ""
    process = db.query(InterviewProcess).filter(InterviewProcess.id == process_id).first()
    if process is None:
        return ""
    return (getattr(process, "company_research", "") or "").strip()


def render_digest(payload: Any) -> str | None:
    """Render a parsed research payload into the persisted digest text.

    Returns None when the payload carries no substantive field — a garbage or
    empty JSON object must not persist as if research had succeeded.
    """
    if not isinstance(payload, dict):
        return None

    def _part(key: str) -> str:
        value = str(payload.get(key) or "").strip()
        return value if value and value.lower() != "unknown" else "unknown"

    substantive = [_part(k) for k in ("process", "rounds", "focus")]
    if all(v == "unknown" for v in substantive):
        return None

    parts = [
        f"Interview process: {_part('process')}",
        f"Round structure: {_part('rounds')}",
        f"Focus & question style: {_part('focus')}",
        f"Notes: {_part('notes')}",
    ]
    sources = payload.get("sources")
    if isinstance(sources, list) and sources:
        urls = [str(u).strip() for u in sources[:5] if str(u).strip()]
        if urls:
            parts.append(f"Sources: {'; '.join(urls)}")
    parts.append(f"Confidence: {_part('confidence')}")
    return "\n".join(parts)[:DIGEST_MAX_CHARS]


def _web_cache_key(name: str, args: dict[str, Any]) -> str | None:
    """Identity for cacheable web calls; None when not cacheable.

    Empty queries/URLs are model mistakes, not cache entries: they stay charged
    against the budget so a junk-call loop still exhausts and stops.
    """
    if name == "web_search":
        query = str((args or {}).get("query") or "").strip().lower()
        return f"web_search::{query}" if query else None
    if name == "web_fetch":
        url = str((args or {}).get("url") or "").strip().lower()
        return f"web_fetch::{url}" if url else None
    return None


def _consume_web_budget(budget: dict[str, int], name: str) -> str | None:
    """Charge one web-tool call; returns the exhaustion observation when spent.

    Charging happens before the call, so failed attempts count too — retries
    must not multiply the worst-case time budget.
    """
    if name not in budget:
        return None
    if budget[name] <= 0:
        return (
            f"{_WEB_BUDGET_MARKERS[name]}\n"
            f"{name} budget exhausted for this research; stop researching now."
        )
    budget[name] -= 1
    return None


async def run_web_research(
    llm: Any,
    *,
    system: str,
    user: str,
    search_budget: int = RESEARCH_SEARCH_BUDGET,
    fetch_budget: int = RESEARCH_FETCH_BUDGET,
    max_seconds: float = PROCESS_MAX_SECONDS,
    tool_timeout: float = RESEARCH_TOOL_TIMEOUT_SECONDS,
    max_rounds: int = RESEARCH_MAX_ROUNDS,
) -> str | None:
    """Shared bounded web-research loop: model + web_search/web_fetch tools.

    Returns the model's final content, or ``None`` on timeout / failure.
    Any exception is swallowed — research must never raise into its caller.
    """
    if llm is None:
        return None
    bundle = ToolBundle()
    bundle.extend([search_tool_spec(), web_fetch_tool_spec()])

    budget = {"web_search": max(0, search_budget), "web_fetch": max(0, fetch_budget)}
    cache: dict[str, str] = {}

    async def execute(name: str, args: dict[str, Any]) -> str:
        cache_key = _web_cache_key(name, args or {})
        if cache_key is not None and cache_key in cache:
            return cache[cache_key]
        exhausted = _consume_web_budget(budget, name)
        if exhausted is not None:
            return exhausted
        raw, _status = await invoke_with_timeout(
            bundle, name, args, timeout=tool_timeout
        )
        if cache_key is not None:
            cache[cache_key] = raw
        return raw

    try:
        loop = await asyncio.wait_for(
            run_agent_loop(
                llm,
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                tools=bundle.definitions(),
                execute=execute,
                max_rounds=max_rounds,
                max_tools_per_round=3,
                temperature=0.2,
                wrap_up_hint={
                    "role": "system",
                    "content": (
                        "Wrap up now: output the final JSON object. No tool calls."
                    ),
                },
            ),
            timeout=max_seconds,
        )
    except asyncio.TimeoutError:
        logger.warning("web research timed out (%.0fs)", max_seconds)
        return None
    except Exception as e:  # noqa: BLE001 - research must never raise
        logger.warning("web research failed: %s", e)
        return None
    return loop.final_content or ""


async def research_company_context(
    llm: Any,
    *,
    company: str,
    role: str,
    level: str,
    ui_locale: str | None = None,
    search_budget: int = RESEARCH_SEARCH_BUDGET,
    fetch_budget: int = RESEARCH_FETCH_BUDGET,
    max_seconds: float = PROCESS_MAX_SECONDS,
    tool_timeout: float = RESEARCH_TOOL_TIMEOUT_SECONDS,
) -> str | None:
    """Run the bounded researcher loop; returns the digest text (or None)."""
    if not (company or "").strip():
        return None

    locale_line = f"UI locale: {ui_locale or 'unknown'}"
    system = _RESEARCH_SYSTEM.format(contract=RESEARCH_JSON_CONTRACT)
    user = (
        f"Target company: {company}\n"
        f"Target role: {role}\nLevel: {level}\n{locale_line}\n\n"
        "Research this company's interview process now. Finish with the JSON object only."
    )
    final = await run_web_research(
        llm,
        system=system,
        user=user,
        search_budget=search_budget,
        fetch_budget=fetch_budget,
        max_seconds=max_seconds,
        tool_timeout=tool_timeout,
    )
    if final is None:
        return None
    digest = render_digest(extract_json_object(final))
    if digest is None:
        logger.info(
            "company research output unusable company=%s (len=%s)",
            company,
            len(str(final)),
        )
    return digest


__all__ = [
    "DIGEST_MAX_CHARS",
    "PROCESS_MAX_SECONDS",
    "RESEARCH_FETCH_BUDGET",
    "RESEARCH_SEARCH_BUDGET",
    "STANDALONE_FETCH_BUDGET",
    "STANDALONE_MAX_SECONDS",
    "STANDALONE_SEARCH_BUDGET",
    "blend_company_context",
    "load_session_company_research",
    "needs_company_research",
    "render_digest",
    "research_company_context",
    "run_web_research",
]
