"""Prep-domain tool registry: definitions and execution are colocated; adding a tool changes only this file.

Each long-lived tool has one :class:`ToolSpec` (OpenAI tools schema + handler).
:data:`TOOL_REGISTRY` is the single source of truth for dispatch; :data:`DOMAIN_TOOL_DEFINITIONS`
is derived from the same :data:`_TOOL_SPECS` plus per-call-bound profile/resume
definitions (those four are intentionally *not* in the registry: their schemas
are snapshots, while execution rebinds live ORM rows on every call — see
:func:`execute_prep_tool`). The agent orchestration layer (agent.py) sees only
the registry and is unaware of individual tools, so extending the tool set
requires no changes to the ReAct loop or agent.

Handler signature: ``(args: dict, memory: WorkingMemory) -> (observation, search_hits)``.
Tools that require user input or alter control flow (such as ask_user) do not use the registry and are handled separately by the agent.

Blocking rule: handlers are async but every synchronous DB access runs inside
:func:`asyncio.to_thread` so the event loop never blocks on SQLite. GitHub and
web search execute through shared platform agent tools. Profile / resume
inspection uses the same specs, bound per call via ``api_db_session``.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import desc

from realmock.platform.capabilities.ai.agent import WorkingMemory
from realmock.platform.capabilities.ai.agent.tools import (
    format_observation,
    github_tool_specs,
    openai_tool,
    profile_from_orm,
    profile_tool_specs,
    resume_tool_specs,
    run_code_snippet,
    snapshot_from_payload,
)
from realmock.platform.capabilities.ai.agent.tools.search import execute_web_search
from realmock.platform.capabilities.ai.llm.client.tool_args import parse_tool_arguments
from realmock.platform.capabilities.knowledge.search.web import SearchHit
from realmock.platform.catalogs.company import get_company_context
from realmock.platform.database import api_db_session, sessions_db_session
from realmock.domains.prep.models import PrepMemory
from realmock.domains.prep.schemas import MEMORY_ORIGINS
from realmock.domains.prep.services import (
    create_memory,
    get_memory,
    list_memories,
    memory_tags,
    memory_to_detail,
    memory_to_summary,
)
from realmock.platform.services.candidate_read import (
    get_default_user_profile,
    get_resume_agent_payload,
)

SearchHits = list[SearchHit]
ToolHandler = Callable[[dict[str, Any], WorkingMemory], Awaitable[tuple[str, SearchHits]]]

_WEB_SEARCH_MAX_RESULTS = 3

# Serializes long-term memory inserts from the same process: tool rounds run
# siblings concurrently, and parallel SQLite commits raise "database is locked".
_MEMORY_WRITE_LOCK = asyncio.Lock()

# Idempotency-key marker remembered in working memory: "memory-key:<key>=#<id>".
_MEMORY_KEY_NOTE_PREFIX = "memory-key:"
_IDEMPOTENCY_KEY_MAX_CHARS = 64

_PREP_GITHUB_NAMES = frozenset({
    "github_list_repos",
    "github_get_readme",
    "github_get_repo",
    "github_list_commits",
    "github_get_user",
    "github_get_file",
})


@dataclass(frozen=True)
class ToolSpec:
    """A complete declaration of a domain tool: schema + execution body."""

    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    #: Loading tier: "primary" tools are declared every turn, "secondary"
    #: tools load on demand through ``search_tools`` (descriptions stay
    #: complete either way — tiering only defers declaration, never content).
    tier: str = "primary"
    #: Search aliases (Chinese + English) for ``search_tools`` matching.
    keywords: tuple[str, ...] = ()


#: Loading tiers (capability names, no vendor terms).
TOOL_TIER_PRIMARY = "primary"
TOOL_TIER_SECONDARY = "secondary"


async def _run_web_search(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
    query = str(args.get("query", "") or "")
    if query:
        memory.remember("note", f"search:{query}")
    raw = await execute_web_search(
        {"query": query, "max_results": args.get("max_results") or _WEB_SEARCH_MAX_RESULTS},
        default_max_results=_WEB_SEARCH_MAX_RESULTS,
    )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw, []
    hits = data.get("results") if isinstance(data.get("results"), list) else []
    text = str(data.get("text") or raw)
    return text, hits


async def _run_company_info(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
    del memory
    company = str(args.get("company", "") or "")
    return await asyncio.to_thread(get_company_context, company), []


async def _run_code_exec(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
    del memory
    language = str(args.get("language", "") or "")
    code = str(args.get("code", "") or "")
    try:
        timeout = float(args.get("timeout", 10.0) or 10.0)
    except (TypeError, ValueError):
        timeout = 10.0
    result = await asyncio.to_thread(run_code_snippet, language, code, timeout=timeout)
    return format_observation(result), []


async def _run_quiz(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
    question = str(args.get("question", "") or "")
    qtype = str(args.get("type", "open") or "open")
    memory.remember("quiz", f"{qtype}:{question}")
    return (
        f"Quiz noted; present it in your formal reply and wait for the user: {question} ({qtype})",
        [],
    )


async def _run_take_note(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
    kind = str(args.get("kind", "note") or "note")
    content = str(args.get("content", "") or "").strip()
    if not content:
        return "take_note missing content; nothing recorded.", []
    memory.remember("weak" if kind == "weak_point" else "note", content)
    return f"Saved to working memory ({kind}): {content}", []


def _list_tags_sync() -> str:
    """Synchronous tag listing; always run inside ``asyncio.to_thread``."""
    with sessions_db_session() as db:
        tags = memory_tags(db)
    return json.dumps({"tags": tags}, ensure_ascii=False)


async def _run_memory_list_tags(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
    del args, memory
    return await asyncio.to_thread(_list_tags_sync), []


_MEMORY_LIST_HARD_LIMIT = 50


def _list_summaries_sync(tag: str | None, limit: int) -> str:
    """Synchronous summary listing; always run inside ``asyncio.to_thread``."""
    with sessions_db_session() as db:
        items = [
            memory_to_summary(row).model_dump(mode="json")
            for row in list_memories(db, tag=tag, limit=limit)
        ]
    return json.dumps({"memories": items}, ensure_ascii=False)


async def _run_memory_list_summaries(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
    del memory
    tag = str(args.get("tag") or "").strip() or None
    try:
        limit = int(args.get("limit") or 20)
    except (TypeError, ValueError):
        limit = 20
    limit = max(1, min(_MEMORY_LIST_HARD_LIMIT, limit))
    return await asyncio.to_thread(_list_summaries_sync, tag, limit), []


def _get_detail_sync(memory_id: int) -> str:
    """Synchronous detail load; always run inside ``asyncio.to_thread``."""
    with sessions_db_session() as db:
        row = get_memory(db, memory_id)
        if row is None:
            return json.dumps({"error": "not_found", "id": memory_id}, ensure_ascii=False)
        payload = memory_to_detail(row).model_dump(mode="json")
    # Bound the observation: full turn bodies can be long; the summary already indexed them.
    for key in ("user_input", "agent_output"):
        if isinstance(payload.get(key), str):
            payload[key] = payload[key][:2000]
    return json.dumps(payload, ensure_ascii=False)


async def _run_memory_get_detail(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
    del memory
    try:
        memory_id = int(args.get("id") or 0)
    except (TypeError, ValueError):
        memory_id = 0
    if memory_id <= 0:
        return json.dumps({"error": "invalid_id"}, ensure_ascii=False), []
    return await asyncio.to_thread(_get_detail_sync, memory_id), []


def _normalize_idempotency_key(raw: Any) -> str:
    """Normalize the caller-supplied dedupe key; empty means no dedupe."""
    return str(raw or "").strip()[:_IDEMPOTENCY_KEY_MAX_CHARS]


def _find_key_note_id(memory: WorkingMemory, key: str) -> int | None:
    """Find a previously recorded idempotency-key marker in working memory."""
    prefix = f"{_MEMORY_KEY_NOTE_PREFIX}{key}=#"
    for note in memory.notes:
        idx = str(note).find(prefix)
        if idx < 0:
            continue
        try:
            return int(str(note)[idx + len(prefix):].split()[0])
        except (TypeError, ValueError, IndexError):
            continue
    return None


def _write_memory_sync(
    summary: str, user_input: str, agent_output: str, tags: list[str], origin: str
) -> tuple[int, bool]:
    """Insert one memory row (exact-summary dedupe); runs inside ``asyncio.to_thread``.

    Returns ``(memory_id, deduplicated)``.
    """
    with sessions_db_session() as db:
        existing = (
            db.query(PrepMemory)
            .filter(PrepMemory.summary == summary)
            .order_by(desc(PrepMemory.id))
            .first()
        )
        if existing is not None:
            return int(existing.id), True
        row = create_memory(
            db,
            summary=summary,
            user_input=user_input,
            agent_output=agent_output,
            tags=tags,
            origin=origin,
        )
        return int(row.id), False


async def _run_memory_write(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
    """Durable memory write with turn-level + row-level idempotency.

    Retried turns must not duplicate rows: an explicit ``idempotency_key`` is
    remembered in working memory (same-turn retries hit it), and an exact
    summary match in the store short-circuits re-inserts (cross-turn retries).
    A process-wide lock serializes concurrent inserts from the same tool round
    (SQLite ``database is locked`` under parallel commits).
    """
    summary = str(args.get("summary") or "").strip()
    if not summary:
        return "memory_write missing summary; nothing recorded.", []
    origin = str(args.get("origin") or "agent_note")
    if origin not in MEMORY_ORIGINS:
        origin = "agent_note"
    tags = args.get("tags") if isinstance(args.get("tags"), list) else []
    key = _normalize_idempotency_key(args.get("idempotency_key"))
    async with _MEMORY_WRITE_LOCK:
        if key:
            hit = _find_key_note_id(memory, key)
            if hit is not None:
                return json.dumps(
                    {"id": hit, "summary": summary[:200], "deduplicated": True},
                    ensure_ascii=False,
                ), []
        memory_id, deduplicated = await asyncio.to_thread(
            _write_memory_sync,
            summary,
            str(args.get("user_input") or ""),
            str(args.get("agent_output") or ""),
            [str(t) for t in tags],
            origin,
        )
        memory.remember("note", f"Long-term memory #{memory_id}: {summary[:160]}")
        if key:
            memory.remember("note", f"{_MEMORY_KEY_NOTE_PREFIX}{key}=#{memory_id}")
    payload: dict[str, Any] = {"id": memory_id, "summary": summary[:200]}
    if deduplicated:
        payload["deduplicated"] = True
    return json.dumps(payload, ensure_ascii=False), []


#: Per-tool search aliases beyond the shared repo vocabulary.
_GITHUB_KEYWORDS: dict[str, tuple[str, ...]] = {
    "github_list_repos": ("list", "列表", "repositories"),
    "github_get_readme": ("readme", "说明", "文档", "docs"),
    "github_get_repo": ("repo info", "详情", "stars", "star"),
    "github_list_commits": ("commit", "提交", "记录", "history"),
    "github_get_user": ("user", "用户", "author", "作者"),
    "github_get_file": ("file", "文件", "source", "源码", "code"),
}

_REPO_KEYWORDS = ("repo", "github", "仓库", "代码仓", "repository", "代码", "code", "项目", "project")


def _github_tool_spec(name: str) -> ToolSpec:
    shared = next(spec for spec in github_tool_specs(names=frozenset({name})) if spec.name == name)

    async def handler(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
        del memory
        return await shared.handler(args), []

    return ToolSpec(
        name=name,
        description=shared.description,
        parameters=shared.parameters,
        handler=handler,
        tier=TOOL_TIER_SECONDARY,
        keywords=_REPO_KEYWORDS + _GITHUB_KEYWORDS.get(name, ()),
    )


_PROFILE_RESUME_NAMES = frozenset(
    {
        "profile_list_sections",
        "profile_get_section",
        "resume_overview",
        "resume_get_section",
    }
)


def _profile_resume_definitions() -> list[dict[str, Any]]:
    from realmock.platform.capabilities.ai.agent.tools.profile import ProfileSnapshot
    from realmock.platform.capabilities.ai.agent.tools.resume import ResumeSnapshot

    specs = profile_tool_specs(ProfileSnapshot(fields={})) + resume_tool_specs(
        ResumeSnapshot(resume_id=0, filename="", file_type="")
    )
    return [openai_tool(spec) for spec in specs]


async def _run_profile_or_resume(
    name: str, args: dict[str, Any], *, resume_id: int | None
) -> tuple[str, SearchHits]:
    """Profile/resume inspection with per-call live binding (never cached across calls).

    Only the ORM snapshot load runs in a worker thread; the bound handler
    itself works on detached in-memory data.
    """
    bound = await asyncio.to_thread(_load_profile_or_resume_spec, name, resume_id)
    if isinstance(bound, str):
        return bound, []
    return await bound.handler(args), []


def _load_profile_or_resume_spec(name: str, resume_id: int | None) -> Any:
    """Load one bound profile/resume spec; returns a JSON error string when unresolvable.

    Always run inside ``asyncio.to_thread`` (synchronous ORM access).
    """
    with api_db_session() as api_db:
        if name.startswith("profile_"):
            specs = {
                spec.name: spec
                for spec in profile_tool_specs(profile_from_orm(get_default_user_profile(api_db)))
            }
            bound = specs.get(name)
            if bound is None:
                return json.dumps({"error": "unknown_tool", "name": name}, ensure_ascii=False)
            return bound
        payload = get_resume_agent_payload(api_db, resume_id)
        if payload is None:
            return json.dumps({"error": "no_resume_bound"}, ensure_ascii=False)
        specs = {spec.name: spec for spec in resume_tool_specs(snapshot_from_payload(payload))}
        bound = specs.get(name)
        if bound is None:
            return json.dumps({"error": "unknown_tool", "name": name}, ensure_ascii=False)
        return bound


_TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="web_search",
        description="Search public interview tips / tech material. Use only when you need timely info.",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
        handler=_run_web_search,
    ),
    ToolSpec(
        name="company_info",
        description="Look up the target company's interview style, focus areas, and sample questions.",
        parameters={
            "type": "object",
            "properties": {
                "company": {
                    "type": "string",
                    "description": "Company id, e.g. bytedance / tencent",
                },
            },
            "required": ["company"],
        },
        handler=_run_company_info,
    ),
    ToolSpec(
        name="code_exec",
        description=(
            "Run a short Python or JavaScript snippet in a temp workspace and read "
            "its stdout/stderr/exit code. Use it to verify an algorithm, reproduce "
            "a bug, or check a computation before concluding — prefer running over "
            "guessing. Include prints for values to inspect; keep snippets small "
            "(~15s max, output truncated)."
        ),
        parameters={
            "type": "object",
            "properties": {
                "language": {
                    "type": "string",
                    "enum": ["python", "javascript"],
                    "description": "Snippet language",
                },
                "code": {
                    "type": "string",
                    "description": "Complete runnable snippet",
                },
                "timeout": {
                    "type": "number",
                    "description": "Seconds before kill (default 10, max 15)",
                },
            },
            "required": ["language", "code"],
        },
        handler=_run_code_exec,
    ),
    ToolSpec(
        name="quiz",
        description="Give the candidate a practice question (multiple-choice or open).",
        parameters={
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "type": {
                    "type": "string",
                    "enum": ["choice", "open"],
                    "description": "Question type",
                },
            },
            "required": ["question"],
        },
        handler=_run_quiz,
    ),
    ToolSpec(
        name="take_note",
        description=(
            "Write a note into session working memory (visible in later turns): "
            "user weak spots, confirmed target role/company, or key conclusions."
        ),
        parameters={
            "type": "object",
            "properties": {
                "kind": {
                    "type": "string",
                    "enum": ["note", "weak_point"],
                    "description": "note=general point, weak_point=user weak spot",
                },
                "content": {"type": "string"},
            },
            "required": ["kind", "content"],
        },
        handler=_run_take_note,
    ),
    ToolSpec(
        name="memory_list_tags",
        description=(
            "List distinct long-term memory tags (most-recently-used first). "
            "Call before memory_write to avoid duplicate topics."
        ),
        parameters={"type": "object", "properties": {}},
        handler=_run_memory_list_tags,
        tier=TOOL_TIER_SECONDARY,
        keywords=("memory", "tag", "记忆", "标签", "tags", "index", "索引"),
    ),
    ToolSpec(
        name="memory_list_summaries",
        description=(
            "List long-term memory index entries (id/summary/tags, newest first). "
            "Check before memory_write to avoid duplicates; use memory_get_detail for full text."
        ),
        parameters={
            "type": "object",
            "properties": {
                "tag": {"type": "string", "description": "Filter by one tag"},
                "limit": {"type": "integer", "description": "Max entries (default 20)"},
            },
        },
        handler=_run_memory_list_summaries,
        tier=TOOL_TIER_SECONDARY,
        keywords=("memory", "summary", "记忆", "摘要", "summaries", "index", "索引", "list"),
    ),
    ToolSpec(
        name="memory_get_detail",
        description="Load one long-term memory with its full user input and agent output.",
        parameters={
            "type": "object",
            "properties": {"id": {"type": "integer"}},
            "required": ["id"],
        },
        handler=_run_memory_get_detail,
        tier=TOOL_TIER_SECONDARY,
        keywords=("memory", "detail", "记忆", "详情", "full text", "全文"),
    ),
    ToolSpec(
        name="memory_write",
        description=(
            "Record a durable long-term memory (user facts, preferences, rated feedback). "
            "Summary must be one line (≤200 chars), topic-organized; only record what "
            "future turns cannot infer. Never record turn trivia. "
            "Before writing, use search_tools to find the memory query tools and "
            "check for duplicate topics."
        ),
        parameters={
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "One-line index (required)"},
                "user_input": {"type": "string"},
                "agent_output": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "origin": {
                    "type": "string",
                    "enum": ["user_rating", "user_emphasis", "agent_note"],
                },
                "idempotency_key": {
                    "type": "string",
                    "description": (
                        "Optional dedupe key for retried turns (e.g. a stable topic id). "
                        "Repeating a key returns the existing memory instead of inserting a duplicate."
                    ),
                },
            },
            "required": ["summary"],
        },
        handler=_run_memory_write,
    ),
] + [_github_tool_spec(name) for name in sorted(_PREP_GITHUB_NAMES)]

TOOL_REGISTRY: dict[str, ToolSpec] = {spec.name: spec for spec in _TOOL_SPECS}

#: On-demand loading catalog: secondary-tier specs searchable through ``search_tools``.
SECONDARY_TOOLS: dict[str, ToolSpec] = {
    spec.name: spec for spec in _TOOL_SPECS if spec.tier == TOOL_TIER_SECONDARY
}

#: Max candidates returned per search call.
_SEARCH_MAX_RESULTS = 5


def _first_sentence(text: str) -> str:
    """One-line summary of a description (first sentence, bounded)."""
    flat = " ".join(str(text or "").split())
    for sep in (". ", "。", ".\n"):
        if sep in flat:
            flat = flat.split(sep, 1)[0]
            break
    return flat[:160].rstrip(". ")


def search_specs(query: str, limit: int = _SEARCH_MAX_RESULTS) -> list[ToolSpec]:
    """Rank secondary tools by name, keyword, then description match.

    Scoring is intentionally transparent: exact name hit (3) beats keyword
    hit (2) beats description hit (1); ties keep registry order (stable).
    Keyword matching runs both directions so multi-character Chinese queries
    ("记忆标签") still hit single-word aliases ("记忆"). Never raises.
    """
    needle = str(query or "").strip().lower()
    if not needle:
        return []
    ranked: list[tuple[int, int, ToolSpec]] = []
    for order, spec in enumerate(SECONDARY_TOOLS.values()):
        if not spec.name:
            continue
        score = 0
        if needle in spec.name.lower():
            score = 3
        elif any(kw.lower() in needle or needle in kw.lower() for kw in spec.keywords if kw):
            score = 2
        elif needle in spec.description.lower():
            score = 1
        if score:
            ranked.append((score, order, spec))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [spec for _, _, spec in ranked[: max(1, limit)]]


def mini_spec(spec: ToolSpec) -> dict[str, Any]:
    """Compact candidate card: name, one-line summary, and parameter names only."""
    properties = spec.parameters.get("properties", {}) if isinstance(spec.parameters, dict) else {}
    return {
        "name": spec.name,
        "summary": _first_sentence(spec.description),
        "params": sorted(str(k) for k in properties.keys()),
    }


async def _run_search_tools(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
    """Find on-demand tools by keyword; optionally select some to load now.

    Single-call semantics: ``select`` names full schemas for the loop, which
    appends them to this turn's toolset (next round callable). Unknown names
    are reported with the valid catalog instead of failing.
    """
    del memory
    query = str(args.get("query", "") or "")
    raw_select = args.get("select", [])
    select = [str(n) for n in raw_select] if isinstance(raw_select, list) else []
    candidates = search_specs(query)
    loaded = [n for n in select[:_SEARCH_MAX_RESULTS] if n in SECONDARY_TOOLS]
    unknown = [n for n in select[:_SEARCH_MAX_RESULTS] if n not in SECONDARY_TOOLS]
    payload: dict[str, Any] = {
        "candidates": [mini_spec(spec) for spec in candidates],
        "loaded": loaded,
        "unknown": unknown,
    }
    if unknown:
        payload["catalog"] = sorted(SECONDARY_TOOLS)
    return json.dumps(payload, ensure_ascii=False), []


_SEARCH_TOOLS_SPEC = ToolSpec(
    name="search_tools",
    description=(
        "Find on-demand tools by keyword when the declared tools lack what this "
        "turn needs (repository tools, memory query tools). Returns matching "
        "candidates with one-line summaries; names passed in select are loaded "
        "immediately and become callable next round, at most once per turn."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Keywords for the capability needed, e.g. repo file, memory tags",
            },
            "select": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Candidate names to load now (optional)",
            },
        },
        "required": ["query"],
    },
    handler=_run_search_tools,
)

_TOOL_SPECS.append(_SEARCH_TOOLS_SPEC)
TOOL_REGISTRY[_SEARCH_TOOLS_SPEC.name] = _SEARCH_TOOLS_SPEC
SECONDARY_TOOLS.pop(_SEARCH_TOOLS_SPEC.name, None)

#: Turn-start static subset: name-gated tools load only when relevant.
#: Predicates take (user_text, resume_id); anything unlisted is always loaded.
_TOOL_AVAILABILITY: dict[str, Any] = {}


def _mentions_repo(user_text: str, resume_id: int | None) -> bool:
    """Repository signals in the turn input (repo talk only)."""
    del resume_id
    text = str(user_text or "")
    return bool(
        re.search(r"github\.com|owner\s*/\s*repo|\brepo\b|仓库|代码仓", text, re.IGNORECASE)
    )


def _has_resume(user_text: str, resume_id: int | None) -> bool:
    """Resume inspection needs a bound resume."""
    del user_text
    return resume_id is not None


_TOOL_AVAILABILITY.update(
    {name: _mentions_repo for name in _PREP_GITHUB_NAMES}
    | {"resume_overview": _has_resume, "resume_get_section": _has_resume}
)


def tool_available(name: str, user_text: str, resume_id: int | None) -> bool:
    """Whether a named tool joins this turn's declarations. Never raises."""
    try:
        predicate = _TOOL_AVAILABILITY.get(name)
        if predicate is None:
            return True
        return bool(predicate(user_text, resume_id))
    except Exception:
        return True


def preload_secondary(name: str, user_text: str, resume_id: int | None) -> bool:
    """Whether an on-demand tool preloads this turn on a matched signal gate.

    Only signal-gated secondary tools (repo talk) preload; pure on-demand
    tools (memory queries) wait for an explicit ``search_tools`` call.
    Never raises.
    """
    try:
        gate = _TOOL_AVAILABILITY.get(name)
        if gate is None:
            return False
        return bool(gate(user_text, resume_id))
    except Exception:
        return False

#: Agent-invoked context compaction (auto mode only). Declared here so the
#: model sees one tool schema source, but intentionally NOT in the registry:
#: execution rewrites agent history and must run inside the turn loop
#: (``PrepAgent._compact_current_round``), which plain handlers cannot reach.
async def _run_compact_out_of_loop(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
    """Fallback for out-of-loop direct dispatch (never fires in the turn loop)."""
    del args, memory
    return "compact_context runs inside the turn loop only; it cannot fold history from here.", []


_COMPACT_TOOL_SPEC = ToolSpec(
    name="compact_context",
    description=(
        "Context compaction: fold older conversation turns into a sectioned summary to free context. "
        "Decide carefully before calling (at most once per turn): remaining space "
        "decides first — when plenty of context remains, do NOT compact even if the "
        "topic shifts; when space runs low, weigh relevance — compact only when "
        "earlier turns barely matter for the current task, and keep them when they "
        "are highly relevant. A still-short conversation is refused automatically. "
        "Never call it as the first action of a turn — think and work first "
        "(search, read, reason), and compact only when mid-turn pressure is "
        "real; an early blind fold burns context you have not used yet. "
        "Everything before the current user message is summarized (objectives, "
        "decisions, findings, to-dos are preserved) while the current turn stays "
        "verbatim. Tune the run with focus (what the summary must prioritize) and "
        "intensity (light keeps more verbatim detail, aggressive folds harder); "
        "both fall back to the session defaults when omitted."
    ),
    parameters={
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "One line on why compaction helps this turn (optional)",
            },
            "focus": {
                "type": "string",
                "description": (
                    "Compression focus for this run: what the summary must "
                    "prioritize, e.g. error stacks, confirmed plans, weak spots "
                    "(optional, max 500 chars)"
                ),
            },
            "intensity": {
                "type": "string",
                "enum": ["light", "balanced", "aggressive"],
                "description": (
                    "Compression amplitude for this run: light keeps more "
                    "verbatim detail, aggressive folds harder (optional)"
                ),
            },
        },
    },
    handler=_run_compact_out_of_loop,
)

COMPACT_TOOL_DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": _COMPACT_TOOL_SPEC.name,
        "description": _COMPACT_TOOL_SPEC.description,
        "parameters": _COMPACT_TOOL_SPEC.parameters,
    },
}

COMPACT_TOOL_NAME = _COMPACT_TOOL_SPEC.name

DOMAIN_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters,
        },
    }
    for spec in _TOOL_SPECS
] + _profile_resume_definitions()

# Backward-compatible alias; prefer :data:`DOMAIN_TOOL_DEFINITIONS` for the
# registry subset and :data:`realmock.domains.prep.agents.agent.PREP_TOOL_DEFINITIONS`
# for the complete turn-start set including ``ask_user``.
PREP_TOOL_DEFINITIONS = DOMAIN_TOOL_DEFINITIONS

#: Full OpenAI declarations of on-demand tools, keyed for mid-turn expansion.
#: The turn toolset only ever grows by appending these (never reordered),
#: so the cached prefix head stays stable across rounds.
SECONDARY_DEFINITIONS: dict[str, dict[str, Any]] = {
    spec.name: openai_tool(spec) for spec in SECONDARY_TOOLS.values()
}


async def execute_prep_tool(
    name: str,
    args: dict[str, Any],
    memory: WorkingMemory,
    *,
    resume_id: int | None = None,
) -> tuple[str, SearchHits]:
    """Dispatch tools through the registry; return ``(observation_text, search_hits)``."""
    if name in _PROFILE_RESUME_NAMES:
        return await _run_profile_or_resume(name, args, resume_id=resume_id)
    spec = TOOL_REGISTRY.get(name)
    if spec is None:
        return f"Unknown tool: {name}", []
    if not isinstance(args, dict):
        args = parse_tool_arguments(args)
    return await spec.handler(args, memory)


__all__ = [
    "COMPACT_TOOL_DEFINITION",
    "COMPACT_TOOL_NAME",
    "PREP_TOOL_DEFINITIONS",
    "SECONDARY_DEFINITIONS",
    "SECONDARY_TOOLS",
    "TOOL_REGISTRY",
    "TOOL_TIER_PRIMARY",
    "TOOL_TIER_SECONDARY",
    "ToolSpec",
    "execute_prep_tool",
    "mini_spec",
    "preload_secondary",
    "search_specs",
    "tool_available",
]
