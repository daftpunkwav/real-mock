"""Interview tools dispatch through shared platform search."""

from __future__ import annotations

import asyncio
import json

from realmock.domains.interview.agents import tools as interview_tools


def test_web_search_interview_exp_uses_shared_execute(monkeypatch) -> None:
    seen: list[dict] = []

    async def fake_search(args):
        seen.append(args)
        return json.dumps({"text": f"hits for {args['query']}", "hits": []})

    monkeypatch.setattr(interview_tools, "execute_web_search", fake_search)

    class _Db:
        pass

    result = asyncio.run(
        interview_tools.execute_interview_tool(
            "web_search_interview_exp",
            {"query": "bytedance backend interview"},
            db=_Db(),
        )
    )
    assert seen == [{"query": "bytedance backend interview"}]
    assert "hits for bytedance backend interview" in result
    assert "search_failed" not in result


def test_company_lookup_persists_finding():
    """Company/resume lookups survive compaction via company_findings."""
    import asyncio
    from realmock.domains.interview.agents.tools import execute_interview_tool

    state: dict = {}

    async def run():
        await execute_interview_tool(
            "lookup_company_profile",
            {"company_id": "bytedance"},
            db=None,
            agent_state=state,
        )

    asyncio.run(run())
    findings = state.get("company_findings") or []
    assert findings and findings[0]["tool"] == "lookup_company_profile"
    assert findings[0]["args"] == "bytedance"
    assert "preview" in findings[0]


def test_working_memory_renders_company_findings():
    from realmock.platform.capabilities.ai.agent.working_memory import WorkingMemory

    memory = WorkingMemory.from_state({
        "company_findings": [
            {"tool": "lookup_resume_projects", "args": "fastapi", "preview": "3 matching projects"}
        ]
    })
    rendered = memory.render()
    assert "Verified" in rendered
    assert "lookup_resume_projects" in rendered
