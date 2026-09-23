"""GitHub REST: single repository metadata, README, commits, PR, Issues, files and languages."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING, Any

from .github_http import MAX_TEXT_CHARS
from .rest_ops_common import _clamp_per_page, _content_path, _is_error, _path_segment

if TYPE_CHECKING:
    from .client import GitHubClient


async def _get_repo(client: "GitHubClient", owner: str, repo: str) -> dict[str, Any]:
    """Get individual warehouse metadata."""
    data = await client._get(f"/repos/{_path_segment(owner)}/{_path_segment(repo)}")
    if _is_error(data):
        return data
    return {
        "full_name": data.get("full_name"),
        "description": data.get("description"),
        "language": data.get("language"),
        "languages_url": data.get("languages_url"),
        "stargazers_count": data.get("stargazers_count"),
        "forks_count": data.get("forks_count"),
        "open_issues_count": data.get("open_issues_count"),
        "default_branch": data.get("default_branch"),
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "pushed_at": data.get("pushed_at"),
        "topics": data.get("topics") or [],
        "license": (data.get("license") or {}).get("spdx_id"),
        "html_url": data.get("html_url"),
        "size": data.get("size"),
    }


async def _get_readme(client: "GitHubClient", owner: str, repo: str) -> dict[str, Any]:
    """Get README text (decoded base64)."""
    data = await client._get(
        f"/repos/{_path_segment(owner)}/{_path_segment(repo)}/readme",
        params={"accept": "application/vnd.github.raw"},
    )
    if isinstance(data, dict) and data.get("content") and data.get("encoding") == "base64":
        try:
            raw = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        except Exception as e:
            return {"error": "decode_failed", "message": str(e)}
        return {
            "owner": owner,
            "repo": repo,
            "name": data.get("name", "README"),
            "path": data.get("path"),
            "content": raw[:MAX_TEXT_CHARS],
            "truncated": len(raw) > MAX_TEXT_CHARS,
        }
    if _is_error(data):
        return data
    if isinstance(data, dict) and "raw" in data:
        text = str(data["raw"])
        return {
            "owner": owner,
            "repo": repo,
            "content": text[:MAX_TEXT_CHARS],
            "truncated": len(text) > MAX_TEXT_CHARS,
        }
    return {"error": "readme_unavailable", "owner": owner, "repo": repo}


async def _list_commits(
    client: "GitHubClient",
    owner: str,
    repo: str,
    *,
    per_page: int = 10,
    author: str | None = None,
) -> dict[str, Any]:
    """Lists a summary of recent commits."""
    per_page = _clamp_per_page(per_page, 20)
    params: dict[str, Any] = {"per_page": per_page}
    if author:
        params["author"] = author
    data = await client._get(
        f"/repos/{_path_segment(owner)}/{_path_segment(repo)}/commits", params=params
    )
    if _is_error(data):
        return data
    if not isinstance(data, list):
        return {"error": "unexpected_response"}
    commits = []
    for c in data:
        commit = c.get("commit") or {}
        author_info = commit.get("author") or {}
        commits.append({
            "sha": (c.get("sha") or "")[:8],
            "message": (commit.get("message") or "").split("\n")[0][:200],
            "author": author_info.get("name"),
            "date": author_info.get("date"),
            "html_url": c.get("html_url"),
        })
    return {"owner": owner, "repo": repo, "count": len(commits), "commits": commits}


async def _list_pull_requests(
    client: "GitHubClient",
    owner: str,
    repo: str,
    *,
    state: str = "all",
    per_page: int = 10,
) -> dict[str, Any]:
    """List PRs."""
    per_page = _clamp_per_page(per_page, 20)
    data = await client._get(
        f"/repos/{_path_segment(owner)}/{_path_segment(repo)}/pulls",
        params={"state": state, "per_page": per_page, "sort": "updated"},
    )
    if _is_error(data):
        return data
    if not isinstance(data, list):
        return {"error": "unexpected_response"}
    prs = []
    for p in data:
        prs.append({
            "number": p.get("number"),
            "title": p.get("title"),
            "state": p.get("state"),
            "user": (p.get("user") or {}).get("login"),
            "created_at": p.get("created_at"),
            "merged_at": p.get("merged_at"),
            "html_url": p.get("html_url"),
        })
    return {"owner": owner, "repo": repo, "count": len(prs), "pulls": prs}


async def _list_issues(
    client: "GitHubClient",
    owner: str,
    repo: str,
    *,
    state: str = "all",
    per_page: int = 10,
) -> dict[str, Any]:
    """List Issues (without PRs)."""
    per_page = _clamp_per_page(per_page, 20)
    data = await client._get(
        f"/repos/{_path_segment(owner)}/{_path_segment(repo)}/issues",
        params={"state": state, "per_page": per_page},
    )
    if _is_error(data):
        return data
    if not isinstance(data, list):
        return {"error": "unexpected_response"}
    issues = []
    for i in data:
        if i.get("pull_request"):
            continue
        issues.append({
            "number": i.get("number"),
            "title": i.get("title"),
            "state": i.get("state"),
            "user": (i.get("user") or {}).get("login"),
            "comments": i.get("comments"),
            "created_at": i.get("created_at"),
            "html_url": i.get("html_url"),
        })
    return {"owner": owner, "repo": repo, "count": len(issues), "issues": issues}


async def _get_tree(
    client: "GitHubClient",
    owner: str,
    repo: str,
    *,
    branch: str,
    recursive: bool = True,
) -> dict[str, Any]:
    """Get the git file tree of the branch (recursively with subdirectories by default)."""
    params = {"recursive": "1"} if recursive else None
    data = await client._get(
        f"/repos/{_path_segment(owner)}/{_path_segment(repo)}/git/trees/{_path_segment(branch)}",
        params=params,
    )
    if _is_error(data):
        return data
    if not isinstance(data, dict) or not isinstance(data.get("tree"), list):
        return {"error": "unexpected_response"}
    return {
        "sha": data.get("sha"),
        # Tree entries that exceed the GitHub upper limit are truncated and the evidence collection party should judge the completeness of the evidence accordingly.
        "truncated": bool(data.get("truncated")),
        "tree": [
            {"path": item.get("path"), "type": item.get("type"), "size": item.get("size")}
            for item in data["tree"]
            if isinstance(item, dict)
        ],
    }


async def _get_file_content(
    client: "GitHubClient",
    owner: str,
    repo: str,
    path: str,
    *,
    ref: str | None = None,
) -> dict[str, Any]:
    """Read the contents of the warehouse file (text)."""
    params = {"ref": ref} if ref else None
    data = await client._get(
        f"/repos/{_path_segment(owner)}/{_path_segment(repo)}/contents/{_content_path(path)}",
        params=params,
    )
    if _is_error(data):
        return data
    if isinstance(data, list):
        entries = [
            {"name": e.get("name"), "type": e.get("type"), "path": e.get("path"), "size": e.get("size")}
            for e in data[:50]
        ]
        return {"type": "dir", "path": path, "entries": entries}
    if not isinstance(data, dict):
        return {"error": "unexpected_response"}
    if data.get("type") != "file":
        return {"type": data.get("type"), "path": path, "message": "non-file node"}
    content_b64 = data.get("content") or ""
    try:
        raw = base64.b64decode(content_b64).decode("utf-8", errors="replace")
    except Exception as e:
        return {"error": "decode_failed", "message": str(e)}
    return {
        "type": "file",
        "path": data.get("path", path),
        "size": data.get("size"),
        "content": raw[:MAX_TEXT_CHARS],
        "truncated": len(raw) > MAX_TEXT_CHARS,
        "html_url": data.get("html_url"),
    }


async def _get_languages(client: "GitHubClient", owner: str, repo: str) -> dict[str, Any]:
    """Warehouse language proportion."""
    data = await client._get(
        f"/repos/{_path_segment(owner)}/{_path_segment(repo)}/languages"
    )
    if _is_error(data):
        return data
    if not isinstance(data, dict):
        return {"error": "unexpected_response"}
    total = sum(v for v in data.values() if isinstance(v, (int, float))) or 1
    breakdown = {
        k: {"bytes": v, "pct": round(100.0 * v / total, 1)}
        for k, v in data.items()
        if isinstance(v, (int, float))
    }
    return {"owner": owner, "repo": repo, "languages": breakdown}
