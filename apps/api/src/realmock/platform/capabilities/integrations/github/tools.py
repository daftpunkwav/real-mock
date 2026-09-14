"""GitHub tool definition and executor (OpenAI function calling format)."""

from __future__ import annotations

import json
import logging
from typing import Any

from realmock.platform.capabilities.integrations.github.client import GitHubClient

logger = logging.getLogger(__name__)

# OpenAI tools[] format; semantics align with the common GitHub MCP surface.
GITHUB_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "github_get_user",
            "description": (
                "Fetch a GitHub user's public profile (bio, public repo count, "
                "followers). Use it to verify who the candidate is on GitHub "
                "and how active they are."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {"type": "string", "description": "GitHub username"},
                },
                "required": ["username"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_list_repos",
            "description": (
                "List the candidate's public GitHub repositories, most recently "
                "updated first. Use it to compare the repos against the resume's "
                "project list."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "username": {"type": "string"},
                    "per_page": {
                        "type": "integer",
                        "description": "Max repos to return (default 10, cap 30)",
                    },
                },
                "required": ["username"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_get_repo",
            "description": (
                "Fetch one repository's metadata (stars, primary language, "
                "last update, topics)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                },
                "required": ["owner", "repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_get_readme",
            "description": (
                "Read a repository's README. Use it to understand the project's "
                "purpose and architecture."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                },
                "required": ["owner", "repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_list_commits",
            "description": (
                "List a repository's most recent commits. Use it to verify "
                "whether the candidate actually develops the project and how "
                "often they contribute."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "author": {
                        "type": "string",
                        "description": "Optional: filter by author login",
                    },
                    "per_page": {"type": "integer"},
                },
                "required": ["owner", "repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_list_pulls",
            "description": (
                "List a repository's pull requests. Use it to assess the "
                "candidate's collaboration and code review experience."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "state": {"type": "string", "enum": ["open", "closed", "all"]},
                    "per_page": {"type": "integer"},
                },
                "required": ["owner", "repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_list_issues",
            "description": (
                "List a repository's issues. Use it to understand known "
                "problems and maintenance activity."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "state": {"type": "string", "enum": ["open", "closed", "all"]},
                    "per_page": {"type": "integer"},
                },
                "required": ["owner", "repo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_get_file",
            "description": (
                "Read a file, or list a directory, at a path inside the "
                "repository. Use it to inspect the tech stack, entry points, "
                "and configuration."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                    "path": {
                        "type": "string",
                        "description": "e.g. README.md or src/main.py",
                    },
                    "ref": {
                        "type": "string",
                        "description": "Optional branch, tag, or commit SHA",
                    },
                },
                "required": ["owner", "repo", "path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_get_languages",
            "description": (
                "Fetch a repository's language breakdown by byte share. Use it "
                "to check whether the resume's claimed stack matches the code."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "owner": {"type": "string"},
                    "repo": {"type": "string"},
                },
                "required": ["owner", "repo"],
            },
        },
    },
]

_GITHUB_TOOL_NAMES = {t["function"]["name"] for t in GITHUB_TOOL_DEFINITIONS}


async def execute_github_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    client: GitHubClient | None = None,
) -> str:
    """Execute the GitHub tool and return a JSON string (for tool role message)."""
    if name not in _GITHUB_TOOL_NAMES:
        return json.dumps({"error": "unknown_github_tool", "name": name}, ensure_ascii=False)

    gh = client or GitHubClient()
    try:
        if name == "github_get_user":
            result = await gh.get_user(str(arguments.get("username", "")))
        elif name == "github_list_repos":
            result = await gh.list_repos(
                str(arguments.get("username", "")),
                per_page=int(arguments.get("per_page") or 10),
            )
        elif name == "github_get_repo":
            result = await gh.get_repo(str(arguments["owner"]), str(arguments["repo"]))
        elif name == "github_get_readme":
            result = await gh.get_readme(str(arguments["owner"]), str(arguments["repo"]))
        elif name == "github_list_commits":
            result = await gh.list_commits(
                str(arguments["owner"]),
                str(arguments["repo"]),
                per_page=int(arguments.get("per_page") or 10),
                author=arguments.get("author"),
            )
        elif name == "github_list_pulls":
            result = await gh.list_pull_requests(
                str(arguments["owner"]),
                str(arguments["repo"]),
                state=str(arguments.get("state") or "all"),
                per_page=int(arguments.get("per_page") or 10),
            )
        elif name == "github_list_issues":
            result = await gh.list_issues(
                str(arguments["owner"]),
                str(arguments["repo"]),
                state=str(arguments.get("state") or "all"),
                per_page=int(arguments.get("per_page") or 10),
            )
        elif name == "github_get_file":
            result = await gh.get_file_content(
                str(arguments["owner"]),
                str(arguments["repo"]),
                str(arguments.get("path", "")),
                ref=arguments.get("ref"),
            )
        elif name == "github_get_languages":
            result = await gh.get_languages(str(arguments["owner"]), str(arguments["repo"]))
        else:
            result = {"error": "unhandled", "name": name}
    except KeyError as e:
        result = {"error": "missing_argument", "detail": str(e)}
    except Exception as e:
        logger.warning("GitHub tool execution failed name=%s err=%s", name, e)
        result = {"error": "execution_failed", "message": str(e)[:300]}

    return json.dumps(result, ensure_ascii=False, default=str)
