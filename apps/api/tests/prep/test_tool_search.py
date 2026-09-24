"""Tiered tool loading: static subsets per turn + search_tools mid-turn expansion."""

from __future__ import annotations

import asyncio
import json

from realmock.domains.prep.agents.agent import PrepAgent
from realmock.domains.prep.agents.tools import (
    SECONDARY_TOOLS,
    TOOL_REGISTRY,
    mini_spec,
    search_specs,
    tool_available,
)


class _FakeLLM:
    """Scripted chat_message replies recording the declared tools per round."""

    context_window = 128000

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0
        self.tools_seen: list[list[str]] = []
        self.usage = None

    async def chat_message(self, messages, temperature=0.7, tools=None, **kwargs):
        del messages, temperature, kwargs
        self.tools_seen.append(
            [str((t.get("function") or {}).get("name")) for t in (tools or [])]
        )
        idx = min(self.calls, len(self.replies) - 1)
        self.calls += 1
        return self.replies[idx]


class _FakeSession:
    messages = "[]"
    resume_id = None
    target_company = ""
    token_usage = 0
    prompt_tokens = 0
    completion_tokens = 0
    cached_tokens = 0


class _FakeDB:
    def commit(self):
        pass


def _tool_call(name: str, args: dict) -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
        ],
    }


# ── Search relevance ─────────────────────────────────────────────────────────


def test_search_specs_rank_name_over_keyword() -> None:
    hits = search_specs("github_get_file")
    assert hits and hits[0].name == "github_get_file"
    hits = search_specs("仓库文件")
    names = [s.name for s in hits]
    assert "github_get_file" in names
    # Keyword matching still reaches the remaining memory detail tool.
    hits = search_specs("记忆详情")
    assert hits and hits[0].name == "memory_get_detail"


def test_search_specs_empty_query_matches_nothing() -> None:
    assert search_specs("") == []
    assert search_specs("   ") == []


def test_mini_spec_carries_params_not_schema() -> None:
    card = mini_spec(TOOL_REGISTRY["github_get_file"])
    assert card["name"] == "github_get_file"
    assert isinstance(card["summary"], str) and card["summary"]
    assert "owner" in card["params"] or "repo" in card["params"]
    assert "description" not in card


def test_secondary_catalog_is_the_agreed_eight() -> None:
    # 6 github tools + the deep memory detail tool + web_fetch load on demand;
    # the cheap memory index tools are declared every turn (no search_tools
    # friction before a dedupe check).
    assert set(SECONDARY_TOOLS) == {
        "github_list_repos",
        "github_get_readme",
        "github_get_repo",
        "github_list_commits",
        "github_get_user",
        "github_get_file",
        "memory_get_detail",
        "web_fetch",
    }


# ── Static per-turn subset ───────────────────────────────────────────────────


def test_tool_available_gates() -> None:
    assert tool_available("web_search", "hello", None) is True
    assert tool_available("search_tools", "hello", None) is True
    assert tool_available("github_get_file", "see https://github.com/a/b", None) is True
    assert tool_available("github_get_file", "interview tips", None) is False
    assert tool_available("resume_overview", "hello", None) is False
    assert tool_available("resume_overview", "hello", 3) is True
    assert tool_available("unknown_tool_xyz", "hello", None) is True


def test_tool_definitions_filter_per_turn() -> None:
    agent = PrepAgent(_FakeSession(), _FakeLLM([]))  # type: ignore[arg-type]

    def names(defs):
        return {str((d.get("function") or {}).get("name")) for d in defs}

    plain = names(agent._tool_definitions("interview tips"))
    assert "search_tools" in plain and "compact_context" in plain
    assert "web_search" in plain
    assert not any(n.startswith("github_") for n in plain)
    assert "resume_overview" not in plain

    repo = names(agent._tool_definitions("review https://github.com/a/b"))
    assert "github_get_file" in repo
    # Cheap memory index tools are first-tier (declared every turn); only the
    # deep detail read waits for search_tools.
    assert "memory_list_tags" in repo
    assert "memory_list_summaries" in repo
    assert "memory_get_detail" not in repo

    agent.session.resume_id = 3
    bound = names(agent._tool_definitions("hello"))
    assert "resume_overview" in bound


# ── Mid-turn expansion ───────────────────────────────────────────────────────


def test_search_expands_turn_tools_for_next_round() -> None:
    search_round = _tool_call("search_tools", {"query": "repo files", "select": ["github_get_file"]})
    done_round = {"role": "assistant", "content": "done", "tool_calls": None}
    llm = _FakeLLM([search_round, done_round])
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]
    # No repo signal in the turn input, so github tools preload nothing and
    # the search path is what loads the schema.
    working = [{"role": "user", "content": "I need the project file list"}]

    async def run():
        return await agent._run_tool_rounds(working, _FakeDB(), asked_user={"on": False})  # type: ignore[arg-type]

    messages, early, groups, steps, thinking = asyncio.run(run())
    assert any(s.get("name") == "search_tools" for s in steps)
    assert "github_get_file" in llm.tools_seen[1], "round 2 must see the expanded schema"
    assert "github_get_file" not in llm.tools_seen[0], "round 1 declares the static subset only"
    # Prefix head stays stable: expansion only appends.
    assert llm.tools_seen[1][: len(llm.tools_seen[0])] == llm.tools_seen[0]


def test_search_expansion_guard_allows_single_load() -> None:
    search_round = _tool_call("search_tools", {"query": "x", "select": ["github_get_user"]})
    search_again = _tool_call("search_tools", {"query": "y", "select": ["github_get_repo"]})
    done_round = {"role": "assistant", "content": "done", "tool_calls": None}
    llm = _FakeLLM([search_round, search_again, done_round])
    agent = PrepAgent(_FakeSession(), llm)  # type: ignore[arg-type]

    async def run():
        return await agent._run_tool_rounds(
            [{"role": "user", "content": "hi"}], _FakeDB(), asked_user={"on": False}  # type: ignore[arg-type]
        )

    messages, early, groups, steps, thinking = asyncio.run(run())
    search_steps = [s for s in steps if s.get("name") == "search_tools"]
    assert len(search_steps) == 2
    assert "already expanded" in (search_steps[1].get("result") or "")
    assert "github_get_repo" not in llm.tools_seen[2]


def test_search_unknown_select_reports_catalog() -> None:
    agent = PrepAgent(_FakeSession(), _FakeLLM([]))  # type: ignore[arg-type]

    async def run():
        return await agent._run_named_tool(
            "search_tools", {"query": "zzz-no-match", "select": ["not_a_tool"]}, _FakeDB()  # type: ignore[arg-type]
        )

    text, _ = asyncio.run(run())
    payload = json.loads(text.split("\n")[0])
    assert payload["unknown"] == ["not_a_tool"]
    assert "github_get_file" in payload["catalog"]
