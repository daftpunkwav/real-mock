"""GitHub REST resource method aggregation re-export (keeping client import path unchanged)."""

from __future__ import annotations

from .rest_ops_repo import (
    _get_file_content,
    _get_languages,
    _get_readme,
    _get_repo,
    _get_tree,
    _list_commits,
    _list_issues,
    _list_pull_requests,
)
from .rest_ops_user import _get_user, _list_repos

__all__ = [
    "_get_file_content",
    "_get_languages",
    "_get_readme",
    "_get_repo",
    "_get_tree",
    "_get_user",
    "_list_commits",
    "_list_issues",
    "_list_pull_requests",
    "_list_repos",
]
