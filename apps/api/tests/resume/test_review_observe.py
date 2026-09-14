"""Tool observation helpers for the resume-review live UI."""

from __future__ import annotations

import json

import pytest

from realmock.domains.resume.agents import review as review_mod
from realmock.domains.resume.agents.observe import (
    public_tool_args,
    search_hosts_from_observation,
)


def test_search_hosts_unique_first_seen() -> None:
    payload = json.dumps(
        {
            "results": [
                {"url": "https://www.zhipin.com/job/1"},
                {"url": "https://zhipin.com/job/2"},
                {"url": "https://github.com/me/real-mock"},
                {"url": "not-a-url"},
            ]
        }
    )
    assert search_hosts_from_observation("web_search", payload) == [
        "zhipin.com",
        "github.com",
        "not-a-url",
    ]


def test_search_hosts_ignores_non_search_tools() -> None:
    payload = json.dumps({"results": [{"url": "https://github.com/me/repo"}]})
    assert search_hosts_from_observation("github_get_repo", payload) == []


async def test_tool_step_event_carries_full_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live-UI tool_step events must carry the full tool text, unclipped."""
    raw = "x" * 9000

    async def fake_invoke(bundle, name, args, context=None):
        return raw, "ok"

    monkeypatch.setattr(review_mod, "_invoke_review_tool", fake_invoke)
    events: list[dict] = []
    used: list[str] = []
    execute = review_mod._build_tool_executor(object(), used, events.append)
    returned = await execute("web_search", {"query": "q"})
    assert returned == raw
    done = [e for e in events if e.get("status") == "ok"]
    assert len(done) == 1
    assert done[0]["result"] == raw
    assert "chars omitted" not in done[0]["result"]


def test_public_tool_args_drops_secrets() -> None:
    out = public_tool_args({"query": "agent engineer", "token": "secret", "api_key": "k"})
    assert out["query"] == "agent engineer"
    assert "token" not in out
    assert "api_key" not in out


def test_public_tool_args_serializes_nested_objects() -> None:
    out = public_tool_args({"filters": {"site": "github.com", "limit": 3}})
    assert "github.com" in str(out["filters"])
