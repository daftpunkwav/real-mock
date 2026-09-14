"""GitHub REST: List of users and repositories."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .rest_ops_common import _clamp_per_page, _is_error

if TYPE_CHECKING:
    from .client import GitHubClient


async def _get_user(client: "GitHubClient", username: str) -> dict[str, Any]:
    """Get user public information."""
    data = await client._get(f"/users/{username}")
    if _is_error(data):
        return data
    return {
        "login": data.get("login"),
        "name": data.get("name"),
        "bio": data.get("bio"),
        "public_repos": data.get("public_repos"),
        "followers": data.get("followers"),
        "following": data.get("following"),
        "company": data.get("company"),
        "blog": data.get("blog"),
        "location": data.get("location"),
        "created_at": data.get("created_at"),
        "html_url": data.get("html_url"),
    }


async def _list_repos(
    client: "GitHubClient",
    username: str,
    *,
    sort: str = "updated",
    per_page: int = 10,
) -> dict[str, Any]:
    """List user public repositories (by update time)."""
    per_page = _clamp_per_page(per_page, 30)
    data = await client._get(
        f"/users/{username}/repos",
        params={"sort": sort, "per_page": per_page, "type": "owner"},
    )
    if _is_error(data):
        return data
    if not isinstance(data, list):
        return {"error": "unexpected_response", "raw_type": type(data).__name__}
    repos = []
    for r in data:
        repos.append({
            "name": r.get("name"),
            "full_name": r.get("full_name"),
            "description": r.get("description"),
            "language": r.get("language"),
            "stargazers_count": r.get("stargazers_count"),
            "forks_count": r.get("forks_count"),
            "open_issues_count": r.get("open_issues_count"),
            "updated_at": r.get("updated_at"),
            "html_url": r.get("html_url"),
            "topics": r.get("topics") or [],
            "default_branch": r.get("default_branch"),
        })
    return {"username": username, "count": len(repos), "repos": repos}
