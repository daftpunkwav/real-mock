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
