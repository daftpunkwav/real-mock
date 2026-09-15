"""Observe agent tests for src/realmock/domains/resume/agents/observe.py.

Covers: search_hosts_from_observation tool/json/shape branches, _host_of empty
branch, public_tool_args redaction/truncation branches.
Conventions: no real network/model downloads (all clients mocked); pure logic;
rate limits reset per test.
"""

from __future__ import annotations

import json

import pytest
from realmock.platform.core.ratelimit import reset_rate_limit


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()


def test_observe_gaps() -> None:
    from realmock.domains.resume.agents import observe as mod

    assert mod.search_hosts_from_observation("other_tool", "{}") == []
    assert mod.search_hosts_from_observation("web_search", "not-json") == []
    assert mod.search_hosts_from_observation("web_search", json.dumps({"a": 1})) == []
    assert mod.search_hosts_from_observation(
        "web_search", json.dumps({"results": "bad"})
    ) == []
    hosts = mod.search_hosts_from_observation(
        "web_search", json.dumps({"results": ["https://example.test/a"]})
    )
    assert hosts == ["example.test"]
    assert mod._host_of("") == ""
    out = mod.public_tool_args({"q": [1, 2, 3], "api_key": "secret"})
    assert "api_key" not in out
    assert out["q"] == [1, 2, 3]
