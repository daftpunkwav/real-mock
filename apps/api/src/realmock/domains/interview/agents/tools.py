"""Interview Agent tool registry and executor.

Tool sources:
1. GitHub MCP-style tools (verify real projects)
2. Company knowledge-base queries (structured queries that complement RAG)
3. Résumé-fragment retrieval (local, without vectors)

Execution results are written to agent_state.github_findings / tool_trace for structured long-context memory.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from realmock.platform.capabilities.ai.agent.tools import (
    github_tool_specs,
    openai_tool,
    profile_from_orm,
    profile_tool_specs,
    resume_tool_specs,
    snapshot_from_payload,
    execute_web_fetch,
    execute_web_search,
)
from realmock.platform.capabilities.ai.agent.tools.profile import ProfileSnapshot
from realmock.platform.capabilities.ai.agent.tools.resume import ResumeSnapshot
from realmock.platform.capabilities.integrations.github.tools import execute_github_tool
from realmock.platform.catalogs.company import get_company_context
from realmock.platform.core.security import redact_api_key
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

MAX_TOOL_ROUNDS = 8
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
#: (prep-domain pattern): the model may extend a slow fetch, clamped 5-180s.
_TIMEOUT_SECONDS_PARAM = {
    "type": "number",
    "description": (
        "Optional per-call timeout in seconds (5-180). Raise it only for a "
        "slow page fetch or a large repo scan; keep every other call fast."
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
    if agent_state is None:
        return
    findings = agent_state.setdefault("company_findings", [])
    findings.append({"tool": tool, "args": subject, "preview": result[:2000]})
    if len(findings) > 10:
        del findings[:-10]


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
    # GitHub tools
    if name.startswith("github_"):
        # If username is not passed and the file has github_username, it can be automatically completed.
        args = dict(arguments or {})
        if name in ("github_get_user", "github_list_repos") and not args.get("username"):
            if profile_id:
                with api_db_session() as api_db:
                    p = get_user_profile(api_db, profile_id)
                    gh_user = getattr(p, "github_username", None) if p else None
                    if gh_user:
                        args["username"] = gh_user
        result = await execute_github_tool(name, args)
        # Write to structured memory
        if agent_state is not None:
            findings = agent_state.setdefault("github_findings", [])
            findings.append({"tool": name, "args": args, "preview": result[:2000]})
            # Keep the last 20 items
            if len(findings) > 20:
                del findings[:-20]
        return _cap_result(result)

    if name.startswith("profile_"):
        with api_db_session() as api_db:
            row = (
                get_user_profile(api_db, profile_id)
                if profile_id
                else get_default_user_profile(api_db)
            )
            specs = {spec.name: spec for spec in profile_tool_specs(profile_from_orm(row))}
        bound = specs.get(name)
        if bound is None:
            return json.dumps({"error": "unknown_tool", "name": name}, ensure_ascii=False)
        return _cap_result(await bound.handler(arguments or {}))

    if name.startswith("resume_") and name != "lookup_resume_projects":
        with api_db_session() as api_db:
            payload = get_resume_agent_payload(api_db, resume_id)
        if payload is None:
            return json.dumps({"error": "no_resume_bound"}, ensure_ascii=False)
        specs = {spec.name: spec for spec in resume_tool_specs(snapshot_from_payload(payload))}
        bound = specs.get(name)
        if bound is None:
            return json.dumps({"error": "unknown_tool", "name": name}, ensure_ascii=False)
        return _cap_result(await bound.handler(arguments or {}))

    if name == "lookup_company_profile":
        company_id = str(arguments.get("company_id") or "")
        ctx = get_company_context(company_id)
        result = _cap_result(ctx or f"No company knowledge found: {company_id}")
        _note_company_finding(agent_state, tool=name, subject=company_id, result=result)
        return result

    if name == "lookup_resume_projects":
        if not resume_id:
            return json.dumps({"error": "no_resume_bound"}, ensure_ascii=False)
        with api_db_session() as api_db:
            detail = get_resume_detail(api_db, resume_id)
            if not detail:
                return json.dumps({"error": "resume_not_found"}, ensure_ascii=False)
            filename, profile = detail
        focus = (arguments.get("focus") or "").lower()
        projects = profile.get("projects") or []
        skills = profile.get("skills") or []
        if focus:
            projects = [p for p in projects if focus in json.dumps(p, ensure_ascii=False).lower()]
            skills = [s for s in skills if focus in str(s).lower()]
        payload = {
            "filename": filename,
            "name": profile.get("name"),
            "skills": skills,
            "projects": projects,
            "summary": profile.get("summary") or "",
        }
        result = _cap_result(json.dumps(payload, ensure_ascii=False))
        _note_company_finding(agent_state, tool=name, subject=focus or "*", result=result)
        return result

    if name == "web_fetch":
        raw = await execute_web_fetch(arguments or {})
        return _cap_result(raw)

    if name == "web_search":
        query = str(arguments.get("query") or "")
        if not query:
            return json.dumps({"error": "empty_query"}, ensure_ascii=False)
        try:
            raw = await execute_web_search({"query": query})
            data = json.loads(raw)
            text = str(data.get("text") or raw)
        except Exception as e:
            # Redact before exposing: exception text may carry credentials or
            # token-bearing URLs (platform convention, mirrors prep tool_exec).
            safe_detail = redact_api_key(str(e))[:200]
            logger.warning("web_search failed: %s", safe_detail)
            return json.dumps(
                {"error": "search_failed", "message": safe_detail}, ensure_ascii=False
            )
        return _cap_result(text)

    if name == "search_past_interviews" or name == "read_past_round":
        from realmock.domains.interview.agents import past_records

        if session is None:
            return json.dumps({"error": "no_process_context"}, ensure_ascii=False)
        if name == "search_past_interviews":
            raw = past_records.search_past_interviews(
                db, session, str(arguments.get("query") or "")
            )
        else:
            # Malformed paging args are a model mistake, not a broken tool:
            # answer with an observation instead of raising into ToolGuard,
            # whose breaker would otherwise open the tool after two bad calls.
            try:
                round_no = int(arguments.get("round_no") or 0)
                offset = int(arguments.get("offset") or 0)
            except (TypeError, ValueError):
                return json.dumps(
                    {"error": "invalid_argument", "field": "round_no/offset (integer)"},
                    ensure_ascii=False,
                )
            raw = past_records.read_past_round(db, session, round_no, offset)
        return _cap_result(raw)

    return json.dumps({"error": "unknown_tool", "name": name}, ensure_ascii=False)


__all__ = [
    "MAX_TOOL_RESULT_CHARS",
    "MAX_TOOL_ROUNDS",
    "execute_interview_tool",
    "get_interview_tool_definitions",
]
