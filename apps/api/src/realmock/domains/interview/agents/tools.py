"""Interview Agent tool registry and executor.

Tool sources:
1. GitHub MCP-style tools (verify real projects)
2. Company knowledge-base queries (structured queries that complement RAG)
3. Résumé-fragment retrieval (local, without vectors)

Execution results are written to agent_state.github_findings / tool_trace for structured long-context memory.

Handlers take one :class:`ToolContext` — the session-scoped inputs of the
call — plus the tool name and its arguments, so no handler repeats the whole
keyword list.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from realmock.domains.interview.agents.agent_policies import INTERVIEWER_LOOP
from realmock.platform.capabilities.ai.agent.tools import (
    ToolSpec,
    execute_web_fetch,
    execute_web_search,
    github_tool_specs,
    openai_tool,
    profile_tool_specs,
    resume_tool_specs,
    snapshot_from_payload,
    snapshot_from_profile,
)
from realmock.platform.capabilities.ai.agent.tools.profile import ProfileSnapshot
from realmock.platform.capabilities.ai.agent.tools.resume import ResumeSnapshot
from realmock.platform.capabilities.integrations.github.tools import execute_github_tool
from realmock.platform.catalogs.company import get_company_context
from realmock.platform.core.security import redact_secrets_in_text
from realmock.platform.database import api_db_session
from realmock.platform.services.candidate_read import (
    get_default_user_profile,
    get_resume_agent_payload,
    get_resume_detail,
    get_user_profile,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    pass

#: Interviewer tool-loop round cap: derived from the declared policy table
#: (agent_policies.INTERVIEWER_LOOP) so tuning stays a table edit, not a
#: second literal drifting away from it.
MAX_TOOL_ROUNDS = INTERVIEWER_LOOP.max_rounds
#: Attention cap for one tool observation — NOT a storage cap (1M-window
#: policy): head+tail deterministic excerpt, never a lossy LLM rewrite.
MAX_TOOL_RESULT_CHARS = 24_000

# Non-GitHub local / company tools
_LOCAL_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "lookup_company_profile",
            "description": "Look up the target company's interview style, focus areas, and sample questions (structured KB).",
            "parameters": {
                "type": "object",
                "properties": {
                    "company_id": {
                        "type": "string",
                        "description": "Company id, e.g. bytedance / tencent / alibaba",
                    },
                },
                "required": ["company_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_resume_projects",
            "description": "Extract projects and skills from the resume bound to this session for evidence-based probing.",
            "parameters": {
                "type": "object",
                "properties": {
                    "focus": {
                        "type": "string",
                        "description": "Optional keyword to filter projects/skills",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search public interview tips / tech material (DuckDuckGo). Use only when you need timely info.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_fetch",
            "description": (
                "Fetch ONE public web page found via web_search and "
                "read its actual content. Use it to verify a claim or quote a "
                "source accurately; do not guess page contents without fetching."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Absolute http(s) URL to fetch"},
                },
                "required": ["url"],
            },
        },
    },
]

# Cross-round memory tools (only offered inside a multi-round process that has
# finished earlier rounds)
_PAST_RECORD_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_past_interviews",
            "description": (
                "Keyword-search the transcripts of the candidate's earlier rounds in this "
                "interview process. Use to avoid re-asking and to probe previously weak points."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keywords, e.g. a project name or topic",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_past_round",
            "description": "Page through the full transcript of one earlier round in this process.",
            "parameters": {
                "type": "object",
                "properties": {
                    "round_no": {"type": "integer", "description": "Earlier round number, e.g. 1"},
                    "offset": {
                        "type": "integer",
                        "description": "Turn offset for paging (default 0)",
                    },
                },
                "required": ["round_no"],
            },
        },
    },
]


#: Optional per-call timeout override, injected into every tool schema
#: (prep-domain pattern): the model may extend a slow fetch, clamped 5-60s.
_TIMEOUT_SECONDS_PARAM = {
    "type": "number",
    "description": (
        "Optional per-call timeout in seconds (5-60). Raise it only for a "
        "slow page fetch; keep every other call fast."
    ),
}


def _with_timeout_override(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for tool in tools:
        fn = tool.get("function")
        params = fn.get("parameters") if isinstance(fn, dict) else None
        if isinstance(params, dict):
            props = params.setdefault("properties", {})
            props.setdefault("timeout_seconds", dict(_TIMEOUT_SECONDS_PARAM))
    return tools


def get_interview_tool_definitions(*, include_past_records: bool = False) -> list[dict[str, Any]]:
    """Returns all OpenAI tools definitions available to the interviewer."""
    github = [openai_tool(spec) for spec in github_tool_specs()]
    profile = [openai_tool(spec) for spec in profile_tool_specs(ProfileSnapshot(fields={}))]
    resume = [
        openai_tool(spec)
        for spec in resume_tool_specs(ResumeSnapshot(resume_id=0, filename="", file_type=""))
    ]
    tools = github + list(_LOCAL_TOOL_DEFINITIONS) + profile + resume
    if include_past_records:
        tools += list(_PAST_RECORD_TOOL_DEFINITIONS)
    return _with_timeout_override(tools)


async def _compact_observation(text: str) -> str:
    """Loop hook (compact_observation): our 24k marked excerpt replaces the
    platform's 12k head-only truncation."""
    return _cap_result(text)


def _cap_result(text: str) -> str:
    """Deterministic marked excerpt: the model's own args and the tool's
    closing facts sit at both ends, so a head+tail cut preserves them."""
    blob = text or ""
    if len(blob) <= MAX_TOOL_RESULT_CHARS:
        return blob
    keep = max(2_000, (MAX_TOOL_RESULT_CHARS - 200) // 2)
    return blob[:keep] + f"\n…[middle omitted; original {len(blob)} chars]\n" + blob[-keep:]


def _append_finding(
    agent_state: dict[str, Any] | None,
    key: str,
    *,
    tool: str,
    args: Any,
    result: str,
    keep: int,
) -> None:
    """Append one tool result to a structured memory list (last ``keep`` entries)."""
    if agent_state is None:
        return
    findings = agent_state.setdefault(key, [])
    findings.append({"tool": tool, "args": args, "preview": result[:2000]})
    if len(findings) > keep:
        del findings[:-keep]


def _note_company_finding(
    agent_state: dict[str, Any] | None,
    *,
    tool: str,
    subject: str,
    result: str,
) -> None:
    """Persist a local-knowledge tool result into structured memory.

    Compaction folds old tool pairs away, so company/resume lookups would
    otherwise vanish and get re-issued every few turns; github_* already
    keeps its own findings list — this mirrors it for local lookups.
    """
    _append_finding(
        agent_state,
        "company_findings",
        tool=tool,
        args=subject,
        result=result,
        keep=10,
    )


@dataclass(frozen=True)
class ToolContext:
    """Session-scoped inputs of one tool call.

    The dispatcher collects them once and hands the same context to every
    handler; a handler reads only the fields its own tool needs.
    """

    db: Session
    resume_id: int | None = None
    profile_id: int | None = None
    agent_state: dict[str, Any] | None = None
    session: Any | None = None


#: Uniform handler signature of the dispatcher table. The dispatcher hands
#: every handler the whole execution context; each handler reads only the
#: fields its tool needs.
_ToolHandler = Callable[[ToolContext, str, dict[str, Any]], Awaitable[str]]


def _note_github_finding(
    agent_state: dict[str, Any] | None,
    name: str,
    args: dict[str, Any],
    result: str,
) -> None:
    """Append one github_* result to the structured memory list (last 20 kept)."""
    _append_finding(
        agent_state,
        "github_findings",
        tool=name,
        args=args,
        result=result,
        keep=20,
    )


def _needs_github_username(name: str, args: dict[str, Any]) -> bool:
    """Whether the call omits a username the bound profile can supply."""
    return name in ("github_get_user", "github_list_repos") and not args.get("username")


def _github_username(ctx: ToolContext) -> str:
    """The candidate's GitHub username from the bound profile ("" when absent)."""
    if not ctx.profile_id:
        return ""
    with api_db_session() as api_db:
        row = get_user_profile(api_db, ctx.profile_id)
        username = getattr(row, "github_username", None) if row else None
    return username or ""


async def _run_github_tool(ctx: ToolContext, name: str, arguments: dict[str, Any]) -> str:
    """github_* tools: platform integration plus structured-memory findings."""
    args = dict(arguments or {})
    if _needs_github_username(name, args):
        username = _github_username(ctx)
        if username:
            args["username"] = username
    result = await execute_github_tool(name, args)
    _note_github_finding(ctx.agent_state, name, args, result)
    return _cap_result(result)


def _specs_by_name(specs: Iterable[ToolSpec]) -> dict[str, ToolSpec]:
    """Index tool specs by the name the model calls them with."""
    return {spec.name: spec for spec in specs}


async def _run_spec_tool(
    specs: dict[str, ToolSpec],
    name: str,
    arguments: dict[str, Any],
) -> str:
    """Run a platform tool spec bound by name (unknown name becomes an observation)."""
    bound = specs.get(name)
    if bound is None:
        return json.dumps({"error": "unknown_tool", "name": name}, ensure_ascii=False)
    return _cap_result(await bound.handler(arguments or {}))


def _profile_specs(ctx: ToolContext) -> dict[str, ToolSpec]:
    """profile_* specs bound to the session's profile snapshot."""
    with api_db_session() as api_db:
        row = (
            get_user_profile(api_db, ctx.profile_id)
            if ctx.profile_id
            else get_default_user_profile(api_db)
        )
        return _specs_by_name(profile_tool_specs(snapshot_from_profile(row)))


def _resume_specs(ctx: ToolContext) -> dict[str, ToolSpec] | None:
    """resume_* specs bound to the session's resume payload (None when unbound)."""
    with api_db_session() as api_db:
        payload = get_resume_agent_payload(api_db, ctx.resume_id)
        if payload is None:
            return None
        return _specs_by_name(resume_tool_specs(snapshot_from_payload(payload)))


async def _run_profile_tool(ctx: ToolContext, name: str, arguments: dict[str, Any]) -> str:
    """profile_* tools: platform specs bound to the session's profile snapshot."""
    return await _run_spec_tool(_profile_specs(ctx), name, arguments)


async def _run_resume_tool(ctx: ToolContext, name: str, arguments: dict[str, Any]) -> str:
    """resume_* tools: platform specs bound to the session's resume payload."""
    specs = _resume_specs(ctx)
    if specs is None:
        return json.dumps({"error": "no_resume_bound"}, ensure_ascii=False)
    return await _run_spec_tool(specs, name, arguments)


async def _run_company_profile_tool(ctx: ToolContext, name: str, arguments: dict[str, Any]) -> str:
    """lookup_company_profile: company KB lookup with a structured-memory note."""
    company_id = str(arguments.get("company_id") or "")
    knowledge = get_company_context(company_id)
    result = _cap_result(knowledge or f"No company knowledge found: {company_id}")
    _note_company_finding(ctx.agent_state, tool=name, subject=company_id, result=result)
    return result


def _focused_projects(projects: list[Any], focus: str) -> list[Any]:
    """Projects whose serialized form mentions the focus keyword."""
    if not focus:
        return projects
    return [p for p in projects if focus in json.dumps(p, ensure_ascii=False).lower()]


def _focused_skills(skills: list[Any], focus: str) -> list[Any]:
    """Skills whose text mentions the focus keyword."""
    if not focus:
        return skills
    return [s for s in skills if focus in str(s).lower()]


async def _run_resume_projects_tool(ctx: ToolContext, name: str, arguments: dict[str, Any]) -> str:
    """lookup_resume_projects: local resume-fragment retrieval, focus-filtered."""
    if not ctx.resume_id:
        return json.dumps({"error": "no_resume_bound"}, ensure_ascii=False)
    with api_db_session() as api_db:
        detail = get_resume_detail(api_db, ctx.resume_id)
    if not detail:
        return json.dumps({"error": "resume_not_found"}, ensure_ascii=False)
    filename, profile = detail
    focus = (arguments.get("focus") or "").lower()
    payload = {
        "filename": filename,
        "name": profile.get("name"),
        "skills": _focused_skills(profile.get("skills") or [], focus),
        "projects": _focused_projects(profile.get("projects") or [], focus),
        "summary": profile.get("summary") or "",
    }
    result = _cap_result(json.dumps(payload, ensure_ascii=False))
    _note_company_finding(ctx.agent_state, tool=name, subject=focus or "*", result=result)
    return result


async def _run_web_fetch_tool(ctx: ToolContext, name: str, arguments: dict[str, Any]) -> str:
    """web_fetch: read one public page through the platform tool."""
    raw = await execute_web_fetch(arguments or {})
    return _cap_result(raw)


async def _run_web_search_tool(ctx: ToolContext, name: str, arguments: dict[str, Any]) -> str:
    """web_search: public web search whose failure stays an observation.

    Redact before exposing: exception text may carry credentials or
    token-bearing URLs (platform convention, mirrors prep tool_exec).
    """
    query = str(arguments.get("query") or "")
    if not query:
        return json.dumps({"error": "empty_query"}, ensure_ascii=False)
    try:
        raw = await execute_web_search({"query": query})
        data = json.loads(raw)
        text = str(data.get("text") or raw)
    except Exception as e:
        safe_detail = redact_secrets_in_text(str(e))[:200]
        logger.warning("web_search failed: %s", safe_detail)
        return json.dumps({"error": "search_failed", "message": safe_detail}, ensure_ascii=False)
    return _cap_result(text)


async def _run_past_records_tool(ctx: ToolContext, name: str, arguments: dict[str, Any]) -> str:
    """search_past_interviews / read_past_round: cross-round transcript reads."""
    from realmock.domains.interview.agents import past_records

    if ctx.session is None:
        return json.dumps({"error": "no_process_context"}, ensure_ascii=False)
    if name == "search_past_interviews":
        raw = past_records.search_past_interviews(
            ctx.db, ctx.session, str(arguments.get("query") or "")
        )
    else:
        paging = past_records.past_round_paging(arguments)
        if paging is None:
            return json.dumps(
                {"error": "invalid_argument", "field": "round_no/offset (integer)"},
                ensure_ascii=False,
            )
        raw = past_records.read_past_round(ctx.db, ctx.session, *paging)
    return _cap_result(raw)


#: Prefix families, consulted when the exact-name table has no entry.
_PREFIX_TOOL_HANDLERS: dict[str, _ToolHandler] = {
    "github_": _run_github_tool,
    "profile_": _run_profile_tool,
    "resume_": _run_resume_tool,
}

#: Exact-name handlers. A new exact-name tool is one handler plus one entry
#: here; the dispatcher itself never grows.
_EXACT_TOOL_HANDLERS: dict[str, _ToolHandler] = {
    "lookup_company_profile": _run_company_profile_tool,
    "lookup_resume_projects": _run_resume_projects_tool,
    "web_fetch": _run_web_fetch_tool,
    "web_search": _run_web_search_tool,
    "search_past_interviews": _run_past_records_tool,
    "read_past_round": _run_past_records_tool,
}


def _resolve_tool_handler(name: str) -> _ToolHandler | None:
    """Resolve a tool name to its handler.

    The exact-name table wins over the prefix families: an exact name is
    the more specific rule, so no tool can be captured by a family it does
    not belong to. The families (github_* / profile_* / resume_*) cover the
    platform tools; unknown names return None and become an
    ``unknown_tool`` observation.
    """
    exact = _EXACT_TOOL_HANDLERS.get(name)
    if exact is not None:
        return exact
    for prefix, handler in _PREFIX_TOOL_HANDLERS.items():
        if name.startswith(prefix):
            return handler
    return None


async def execute_interview_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    db: Session,
    resume_id: int | None = None,
    profile_id: int | None = None,
    agent_state: dict[str, Any] | None = None,
    llm: Any | None = None,
    session: Any | None = None,
) -> str:
    """Execute a single tool, returning a string result."""
    handler = _resolve_tool_handler(name)
    if handler is None:
        return json.dumps({"error": "unknown_tool", "name": name}, ensure_ascii=False)
    ctx = ToolContext(
        db=db,
        resume_id=resume_id,
        profile_id=profile_id,
        agent_state=agent_state,
        session=session,
    )
    return await handler(ctx, name, arguments)


__all__ = [
    "MAX_TOOL_RESULT_CHARS",
    "MAX_TOOL_ROUNDS",
    "execute_interview_tool",
    "get_interview_tool_definitions",
]
