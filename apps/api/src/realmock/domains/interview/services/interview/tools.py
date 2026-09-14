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
from typing import Any

from sqlalchemy.orm import Session

from realmock.platform.capabilities.ai.agent.tools import (
    github_tool_specs,
    openai_tool,
    profile_from_orm,
    profile_tool_specs,
    resume_tool_specs,
    snapshot_from_payload,
    execute_web_search,
)
from realmock.platform.capabilities.ai.agent.tools.profile import ProfileSnapshot
from realmock.platform.capabilities.ai.agent.tools.resume import ResumeSnapshot
from realmock.platform.capabilities.ai.context.blobs import compress_text_blob
from realmock.platform.capabilities.ai.llm.tool_args import parse_tool_arguments  # noqa: F401 — Re-export for backward compat (explicit via __all__); prefer direct import.
from realmock.platform.capabilities.integrations.github.tools import execute_github_tool
from realmock.platform.catalogs.company import get_company_context
from realmock.platform.database import api_db_session
from realmock.platform.services.candidate_read import (
    get_default_user_profile,
    get_resume_agent_payload,
    get_resume_detail,
    get_user_profile,
)

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 3
MAX_TOOL_RESULT_CHARS = 8_000

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
            "name": "web_search_interview_exp",
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
                    "query": {"type": "string", "description": "Keywords, e.g. a project name or topic"},
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
                    "offset": {"type": "integer", "description": "Turn offset for paging (default 0)"},
                },
                "required": ["round_no"],
            },
        },
    },
]


def get_interview_tool_definitions(
    *, include_past_records: bool = False
) -> list[dict[str, Any]]:
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
    return tools


async def _cap_result(text: str, llm: Any | None) -> str:
    return await compress_text_blob(
        llm,
        text,
        soft_chars=MAX_TOOL_RESULT_CHARS,
        target_chars=MAX_TOOL_RESULT_CHARS,
        purpose="interview tool result",
    )


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
            findings.append({"tool": name, "args": args, "preview": result[:500]})
            # Keep the last 20 items
            if len(findings) > 20:
                del findings[:-20]
        return await _cap_result(result, llm)

    if name.startswith("profile_"):
        with api_db_session() as api_db:
            row = get_user_profile(api_db, profile_id) if profile_id else get_default_user_profile(api_db)
            specs = {spec.name: spec for spec in profile_tool_specs(profile_from_orm(row))}
        bound = specs.get(name)
        if bound is None:
            return json.dumps({"error": "unknown_tool", "name": name}, ensure_ascii=False)
        return await _cap_result(await bound.handler(arguments or {}), llm)

    if name.startswith("resume_") and name != "lookup_resume_projects":
        with api_db_session() as api_db:
            payload = get_resume_agent_payload(api_db, resume_id)
        if payload is None:
            return json.dumps({"error": "no_resume_bound"}, ensure_ascii=False)
        specs = {spec.name: spec for spec in resume_tool_specs(snapshot_from_payload(payload))}
        bound = specs.get(name)
        if bound is None:
            return json.dumps({"error": "unknown_tool", "name": name}, ensure_ascii=False)
        return await _cap_result(await bound.handler(arguments or {}), llm)

    if name == "lookup_company_profile":
        company_id = str(arguments.get("company_id") or "")
        ctx = get_company_context(company_id)
        return await _cap_result(ctx or f"No company knowledge found: {company_id}", llm)

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
            projects = [
                p for p in projects
                if focus in json.dumps(p, ensure_ascii=False).lower()
            ]
            skills = [s for s in skills if focus in str(s).lower()]
        payload = {
            "filename": filename,
            "name": profile.get("name"),
            "skills": skills[:40],
            "projects": projects[:15],
            "summary": (profile.get("summary") or "")[:800],
        }
        return await _cap_result(json.dumps(payload, ensure_ascii=False), llm)

    if name == "web_search_interview_exp":
        query = str(arguments.get("query") or "")
        if not query:
            return json.dumps({"error": "empty_query"}, ensure_ascii=False)
        try:
            raw = await execute_web_search({"query": query})
            data = json.loads(raw)
            text = str(data.get("text") or raw)
        except Exception as e:
            logger.warning("web_search failed: %s", e)
            return json.dumps({"error": "search_failed", "message": str(e)[:200]}, ensure_ascii=False)
        return await _cap_result(text, llm)

    if name == "search_past_interviews" or name == "read_past_round":
        from realmock.domains.interview.services.interview import past_records

        if session is None:
            return json.dumps({"error": "no_process_context"}, ensure_ascii=False)
        if name == "search_past_interviews":
            raw = past_records.search_past_interviews(db, session, str(arguments.get("query") or ""))
        else:
            raw = past_records.read_past_round(
                db,
                session,
                int(arguments.get("round_no") or 0),
                int(arguments.get("offset") or 0),
            )
        return await _cap_result(raw, llm)

    return json.dumps({"error": "unknown_tool", "name": name}, ensure_ascii=False)


__all__ = [
    "MAX_TOOL_RESULT_CHARS",
    "MAX_TOOL_ROUNDS",
    "execute_interview_tool",
    "get_interview_tool_definitions",
    "parse_tool_arguments",
]
