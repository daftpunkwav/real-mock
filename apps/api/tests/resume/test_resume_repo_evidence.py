"""Repo evidence tests for src/realmock/domains/resume/services/repo_evidence.py.

Covers: extract_github_repos dedup/limit branches, _is_error/_pick_key_files
branches, _evidence_for_repo meta rate-limit/generic/non-dict branches, full
evidence/quota-shed branches, tree-truncated/empty/error-file branches (GitHub
client and quota faked).
Conventions: no real network/model downloads (all clients mocked).
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()


class _FakeGitHub:
    def __init__(self, **overrides):
        self._o = overrides

    async def get_repo(self, owner, repo):
        return self._o.get("repo", {"stargazers_count": 5, "forks_count": 1, "language": "Python", "pushed_at": "2024-01-02T00:00:00Z", "description": "d", "default_branch": "main"})

    async def get_readme(self, owner, repo):
        return self._o.get("readme", {"content": "readme-body"})

    async def get_languages(self, owner, repo):
        return self._o.get("langs", {"Python": 10, "Go": 2})

    async def list_commits(self, owner, repo, per_page=3):
        return self._o.get("commits", [{"commit": {"author": {"date": "2024-01-01T00:00:00Z"}, "message": "feat: x\nbody"}}])

    async def get_tree(self, owner, repo, branch="main"):
        return self._o.get("tree", {"tree": [{"type": "blob", "path": "main.py"}], "truncated": False})

    async def get_file_content(self, owner, repo, path, ref="main"):
        files = self._o.get("files", {"main.py": {"content": "print(1)"}})
        return files.get(path, {"error": "missing"})


def test_extract_github_repos_dedup_limit() -> None:
    from realmock.domains.resume.services.repo_evidence import extract_github_repos

    assert extract_github_repos("") == []
    text = (
        "see https://github.com/Owner/Repo.git, https://github.com/owner/repo. "
        "and https://github.com/a/b#readme plus https://github.com/c/d"
    )
    targets = extract_github_repos(text, limit=10)
    assert [(t.owner, t.repo) for t in targets] == [("Owner", "Repo"), ("a", "b"), ("c", "d")]
    assert targets[0].url == "https://github.com/Owner/Repo"
    capped = extract_github_repos(text, limit=1)
    assert len(capped) == 1
    assert capped[0].notes == []


def test_is_error_and_pick_key_files() -> None:
    from realmock.domains.resume.services.repo_evidence import _is_error, _pick_key_files

    assert _is_error({"error": "x"}) is True
    assert _is_error("nope") is True
    assert _is_error({"stars": 1}) is False
    picked = _pick_key_files(["README.md", "package.json", "main.py", "other.txt", "app.py"], limit=2)
    assert "package.json" in picked
    assert len(picked) == 2
    root = _pick_key_files(["src/nested.py", "run.py"], limit=5)
    assert root == ["run.py"]
    assert _pick_key_files([], limit=2) == []


@pytest.mark.asyncio
async def test_evidence_meta_rate_limit_and_generic(monkeypatch) -> None:
    import realmock.domains.resume.services.repo_evidence as ev

    target = ev.extract_github_repos("https://github.com/o/r")[0]
    out = await ev._evidence_for_repo(_FakeGitHub(repo={"error": "x", "status": 403, "message": "rate limit exceeded"}), target)
    assert any("quota" in n for n in out["evidence_notes"])
    out2 = await ev._evidence_for_repo(_FakeGitHub(repo={"error": "x", "message": "not found"}), target)
    assert any("Failed" in n for n in out2["evidence_notes"])
    # Non-dict meta crashes on .get (implementation assumes dict); document current behavior.
    with pytest.raises(AttributeError):
        await ev._evidence_for_repo(_FakeGitHub(repo="not-a-dict"), target)


@pytest.mark.asyncio
async def test_evidence_full_and_quota_shed(monkeypatch) -> None:
    import realmock.domains.resume.services.repo_evidence as ev

    target = ev.extract_github_repos("https://github.com/o/r")[0]
    out = await ev._evidence_for_repo(_FakeGitHub(), target)
    assert out["stars"] == 5
    assert out["summary"] == "readme-body"
    assert out["languages"] == ["Python", "Go"]
    # NOTE: list_commits branch is currently unreachable: _is_error(list) is True,
    # so a list payload is treated as error and recent_commits is never set.
    # This asserts actual behavior; fixing requires implementation change.
    assert "recent_commits" not in out
    assert out["key_files"][0]["path"] == "main.py"

    monkeypatch.setattr(ev, "get_last_quota", lambda: {"remaining": 1})
    out2 = await ev._evidence_for_repo(_FakeGitHub(), target)
    assert any("quota" in n for n in out2["evidence_notes"])
    assert "key_files" not in out2


@pytest.mark.asyncio
async def test_evidence_tree_truncated_and_empty(monkeypatch) -> None:
    import realmock.domains.resume.services.repo_evidence as ev

    monkeypatch.setattr(ev, "get_last_quota", lambda: {})
    target = ev.extract_github_repos("https://github.com/o/r")[0]
    tree = {"tree": [{"type": "blob", "path": "main.py"}, {"type": "tree", "path": "dir"}, {"path": ""}], "truncated": True}
    out = await ev._evidence_for_repo(
        _FakeGitHub(tree=tree, readme={"error": "x"}, files={}), target
    )
    assert any("truncated" in n for n in out["evidence_notes"])
    assert any("limited" in n for n in out["evidence_notes"])

    out2 = await ev._evidence_for_repo(
        _FakeGitHub(readme={"error": "x"}, langs={"error": "x"}, commits={"error": "x"}, tree={"error": "x"}, files={}),
        target,
    )
    assert any("limited" in n for n in out2["evidence_notes"])

    # error file content is skipped
    out3 = await ev._evidence_for_repo(_FakeGitHub(files={"main.py": {"error": "denied"}}), target)
    assert "key_files" not in out3
