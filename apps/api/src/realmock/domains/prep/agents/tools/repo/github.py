"""Repository tools (GitHub family): kept together, loaded on demand.

All six tools share one factory over platform github specs plus one repo-talk
signal vocabulary. They stay secondary-tier: preloaded only on repo signals,
otherwise discovered via search_tools. A platform tool missing at import time
is skipped with a warning (degraded catalog) instead of failing the import.
"""

from __future__ import annotations

import logging
from typing import Any

from realmock.domains.prep.agents.tools.spec import SearchHits, ToolSpec, TOOL_TIER_SECONDARY
from realmock.platform.capabilities.ai.agent import WorkingMemory
from realmock.platform.capabilities.ai.agent.tools import github_tool_specs

GITHUB_TOOL_NAMES = frozenset({
    "github_list_repos",
    "github_get_readme",
    "github_get_repo",
    "github_list_commits",
    "github_get_user",
    "github_get_file",
})

# Backward-compatible alias.
_PREP_GITHUB_NAMES = GITHUB_TOOL_NAMES

#: Per-tool search aliases beyond the shared repo vocabulary.
_GITHUB_KEYWORDS: dict[str, tuple[str, ...]] = {
    "github_list_repos": ("list", "列表", "repositories"),
    "github_get_readme": ("readme", "说明", "文档", "docs"),
    "github_get_repo": ("repo info", "详情", "stars", "star"),
    "github_list_commits": ("commit", "提交", "记录", "history"),
    "github_get_user": ("user", "用户", "author", "作者"),
    "github_get_file": ("file", "文件", "source", "源码", "code"),
}

REPO_KEYWORDS = ("repo", "github", "仓库", "代码仓", "repository", "代码", "code", "项目", "project")

# Backward-compatible alias.
_REPO_KEYWORDS = REPO_KEYWORDS


logger = logging.getLogger(__name__)


def github_tool_spec(name: str) -> ToolSpec:
    """Build one GitHub ToolSpec from the shared platform spec.

    Raises:
        RuntimeError: When the platform no longer provides ``name``.
    """
    try:
        shared = next(spec for spec in github_tool_specs(names=frozenset({name})) if spec.name == name)
    except StopIteration:
        raise RuntimeError(f"Platform github tool missing: {name}") from None

    async def handler(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
        del memory
        return await shared.handler(args), []

    return ToolSpec(
        name=name,
        description=shared.description,
        parameters=shared.parameters,
        handler=handler,
        tier=TOOL_TIER_SECONDARY,
        keywords=REPO_KEYWORDS + _GITHUB_KEYWORDS.get(name, ()),
    )


def _build_github_specs() -> list[ToolSpec]:
    """Assemble available GitHub specs, skipping platform-missing tools with a warning."""
    specs: list[ToolSpec] = []
    for tool_name in sorted(GITHUB_TOOL_NAMES):
        try:
            specs.append(github_tool_spec(tool_name))
        except RuntimeError as exc:
            logger.warning("Prep GitHub tool unavailable, skipping: %s", exc)
    return specs


GITHUB_SPECS: list[ToolSpec] = _build_github_specs()


__all__ = ["GITHUB_SPECS", "GITHUB_TOOL_NAMES", "REPO_KEYWORDS", "github_tool_spec"]
