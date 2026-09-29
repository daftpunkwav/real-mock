"""Tests for the pre-interview GitHub evidence seeding pass.

Covers: digest rendering from REST fakes, error/fork degradation, the char
cap, and the session-row seeding path (skip when seeded / no username / write).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from realmock.domains.interview.agents.research import github_evidence as ge


def _fake_executor(user=None, repos=None, readme=None, fail_user=False):
    async def _execute(name, arguments):
        if name == "github_get_user":
            if fail_user:
                return json.dumps({"error": "execution_failed", "message": "rate limited"})
            return json.dumps(user or {})
        if name == "github_list_repos":
            # Real executor contract (rest_ops_user._list_repos): a dict with
            # the repo list under "repos", NOT a bare list.
            items = repos or []
            return json.dumps(
                {"username": arguments.get("username"), "count": len(items), "repos": items}
            )
        if name == "github_get_readme":
            return json.dumps(readme or {})
        return json.dumps({"error": "unknown_github_tool", "name": name})

    return _execute


@pytest.mark.asyncio
async def test_gather_evidence_renders_user_repos_readme(monkeypatch) -> None:
    monkeypatch.setattr(
        ge,
        "execute_github_tool",
        _fake_executor(
            user={"login": "octo", "name": "Octo Dev", "public_repos": 12, "bio": "builder"},
            repos=[
                {"name": "forked-thing", "fork": True, "stargazers_count": 500},
                {
                    "name": "web-agent",
                    "stargazers_count": 42,
                    "language": "Python",
                    "description": "An agent framework",
                },
                {"name": "tiny-cli", "stargazers_count": 7, "language": "Go"},
            ],
            readme={"content": "# web-agent\nIt orchestrates tools.", "truncated": True},
        ),
    )
    digest = await ge.gather_evidence("octo")
    assert digest.startswith("GitHub user: Octo Dev (@octo), 12 public repos — builder")
    assert "Top repos:" in digest
    assert "- web-agent stars=42 lang=Python: An agent framework" in digest
    assert "forked-thing" not in digest  # forks are skipped
    assert "README of web-agent (truncated): # web-agent" in digest


@pytest.mark.asyncio
async def test_gather_evidence_user_error_is_empty(monkeypatch) -> None:
    monkeypatch.setattr(ge, "execute_github_tool", _fake_executor(fail_user=True))
    assert await ge.gather_evidence("octo") == ""


@pytest.mark.asyncio
async def test_gather_evidence_no_usable_repos_is_empty(monkeypatch) -> None:
    monkeypatch.setattr(
        ge,
        "execute_github_tool",
        _fake_executor(user={"login": "octo"}, repos=[]),
    )
    assert await ge.gather_evidence("octo") == ""


@pytest.mark.asyncio
async def test_gather_evidence_capped(monkeypatch) -> None:
    monkeypatch.setattr(
        ge,
        "execute_github_tool",
        _fake_executor(
            user={"login": "octo"},
            repos=[{"name": "huge", "stargazers_count": 1}],
            readme={"content": "x" * 10_000},
        ),
    )
    digest = await ge.gather_evidence("octo")
    assert len(digest) <= ge.EVIDENCE_MAX_CHARS


class _FakeDb:
    def __init__(self, session_row):
        self._row = session_row
        self.committed = False

    def get(self, model, row_id):
        return self._row

    def commit(self):
        self.committed = True


def _patch_db(monkeypatch, session_row, profile):
    db = _FakeDb(session_row)

    @staticmethod
    def _fake_sessions_ctx():
        import contextlib

        return contextlib.nullcontext(db)

    @staticmethod
    def _fake_api_ctx():
        import contextlib

        return contextlib.nullcontext(SimpleNamespace())

    monkeypatch.setattr(ge, "sessions_db_session", _fake_sessions_ctx)
    monkeypatch.setattr(ge, "api_db_session", _fake_api_ctx)
    monkeypatch.setattr(ge, "get_user_profile", lambda db, pid: profile)
    return db


@pytest.mark.asyncio
async def test_seed_writes_evidence_to_session_row(monkeypatch) -> None:
    row = SimpleNamespace(github_evidence="", profile_id=5)
    db = _patch_db(monkeypatch, row, SimpleNamespace(github_username="octo"))
    monkeypatch.setattr(
        ge,
        "execute_github_tool",
        _fake_executor(
            user={"login": "octo", "public_repos": 1},
            repos=[{"name": "web-agent", "stargazers_count": 3}],
        ),
    )
    await ge.seed_session_github_evidence(9)
    assert "GitHub user:" in row.github_evidence
    assert db.committed


@pytest.mark.asyncio
async def test_seed_skips_when_already_seeded(monkeypatch) -> None:
    row = SimpleNamespace(github_evidence="already has evidence", profile_id=5)
    db = _patch_db(monkeypatch, row, SimpleNamespace(github_username="octo"))

    async def _boom(name, args):  # must never be called
        raise AssertionError("no GitHub call expected")

    monkeypatch.setattr(ge, "execute_github_tool", _boom)
    await ge.seed_session_github_evidence(9)
    assert row.github_evidence == "already has evidence"
    assert db.committed is False


@pytest.mark.asyncio
async def test_seed_skips_without_username(monkeypatch) -> None:
    row = SimpleNamespace(github_evidence="", profile_id=5)
    db = _patch_db(monkeypatch, row, SimpleNamespace(github_username="  "))

    async def _boom(name, args):
        raise AssertionError("no GitHub call expected")

    monkeypatch.setattr(ge, "execute_github_tool", _boom)
    await ge.seed_session_github_evidence(9)
    assert row.github_evidence == ""
    assert db.committed is False


@pytest.mark.asyncio
async def test_seed_never_raises(monkeypatch) -> None:
    def _explode():
        raise RuntimeError("db down")

    monkeypatch.setattr(ge, "sessions_db_session", _explode)
    await ge.seed_session_github_evidence(9)  # must not raise
