"""Open-source repository evidence gathering for resume evaluations.

Responsibilities:
- Parse GitHub links from resume text
- Fetch verified repository facts via GitHub API (no LLM)
- Degrade every failure to notes / empty list so review can continue

Limits (repo cap, README chars, key-file patterns) live in ``schemas.limits``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from realmock.platform.capabilities.integrations.github.client import GitHubClient
from realmock.platform.capabilities.integrations.github.github_http import (
    LOW_QUOTA_REMAINING,
    get_last_quota,
)
from realmock.domains.resume.schemas.limits import (
    KEY_FILE_PATTERNS,
    MAX_EVIDENCE_COMMITS,
    MAX_EVIDENCE_FILE_CHARS,
    MAX_EVIDENCE_REPOS,
    MAX_README_CHARS,
)

logger = logging.getLogger(__name__)

# github.com/owner/repo (tolerates trailing.git, punctuation, and inline anchors)
_REPO_LINK_RE = re.compile(
    r"github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)",
    re.I,
)


@dataclass
class _RepoTarget:
    owner: str
    repo: str
    url: str
    notes: list[str] = field(default_factory=list)


def extract_github_repos(text: str, limit: int = MAX_EVIDENCE_REPOS) -> list[_RepoTarget]:
    """Extract GitHub repository links from resume text (deduplicated/capped)."""
    seen: set[tuple[str, str]] = set()
    targets: list[_RepoTarget] = []
    for match in _REPO_LINK_RE.finditer(text or ""):
        owner, repo = match.group(1), match.group(2)
        repo = re.sub(r"\.git$", "", repo, flags=re.I).rstrip(".")
        if (owner.lower(), repo.lower()) in seen:
            continue
        seen.add((owner.lower(), repo.lower()))
        targets.append(
            _RepoTarget(owner=owner, repo=repo, url=f"https://github.com/{owner}/{repo}")
        )
        if len(targets) >= limit:
            break
    return targets


def _is_error(data: object) -> bool:
    return not isinstance(data, dict) or "error" in data


def _pick_key_files(tree_paths: list[str], limit: int) -> list[str]:
    """Select key source files from the repository file tree. Prefer KEY_FILE_PATTERNS matches, then fill from root-level sources."""
    lowers = {p: p.lower() for p in tree_paths}
    picked: list[str] = []
    for pattern in KEY_FILE_PATTERNS:
        for path in tree_paths:
            name = lowers[path].rsplit("/", 1)[-1]
            if name == pattern or lowers[path] == pattern:
                if path not in picked:
                    picked.append(path)
                break
    for path in tree_paths:
        if len(picked) >= limit:
            break
        if "/" not in path and lowers[path].endswith((".py", ".rs", ".ts", ".go", ".js")):
            if path not in picked:
                picked.append(path)
    return picked[:limit]


async def _evidence_for_repo(client: GitHubClient, target: _RepoTarget) -> dict:
    """Capture forensic facts of a single repository; on any step failure record in evidence_notes and continue."""
    owner, repo = target.owner, target.repo
    evidence: dict = {"repo": f"{owner}/{repo}", "url": target.url, "evidence_notes": []}

    meta = await client.get_repo(owner, repo)
    if _is_error(meta):
        message = str(meta.get("message", ""))[:200] if isinstance(meta, dict) else ""
        if meta.get("status") == 403 or "rate limit" in message.lower():
            evidence["evidence_notes"].append(
                "The GitHub API quota has been exhausted; "
                "link a GitHub account under Settings → Integrations → GitHub (or set GITHUB_TOKEN) and re-evaluate"
            )
        else:
            evidence["evidence_notes"].append(f"Failed to obtain warehouse metadata:{message or 'unknown error'}")
        return evidence
    evidence.update(
        {
            "stars": meta.get("stargazers_count"),
            "forks": meta.get("forks_count"),
            "language": meta.get("language") or "",
            "last_push": str(meta.get("pushed_at") or "")[:10],
            "description": str(meta.get("description") or "")[:200],
        }
    )

    readme = await client.get_readme(owner, repo)
    if not _is_error(readme):
        content = str(readme.get("content") or "")
        evidence["summary"] = content[:MAX_README_CHARS]

    langs = await client.get_languages(owner, repo)
    if not _is_error(langs):
        evidence["languages"] = list(langs.keys())[:5]

    commits = await client.list_commits(owner, repo, per_page=MAX_EVIDENCE_COMMITS)
    if not _is_error(commits) and isinstance(commits, list):
        evidence["recent_commits"] = [
            {
                "date": str((c.get("commit") or {}).get("author", {}).get("date", ""))[:10],
                "message": str(((c.get("commit") or {}).get("message") or "")).split("\n", 1)[0][:80],
            }
            for c in commits[:MAX_EVIDENCE_COMMITS]
        ]

    # View source code: file tree → select key files to read content
    branch = str(meta.get("default_branch") or "main")
    quota = get_last_quota()
    if quota.get("remaining") is not None and quota["remaining"] < LOW_QUOTA_REMAINING:
        # Advisory process-local reading: shed the heaviest calls first (tree
        # + file contents) while keeping the light core evidence above.
        evidence["evidence_notes"].append(
            f"GitHub quota nearly exhausted (about {quota['remaining']} remaining); "
            "source-tree evidence skipped for this repository."
        )
        tree = {"error": "quota_shed"}
    else:
        tree = await client.get_tree(owner, repo, branch=branch)
    paths: list[str] = []
    if not _is_error(tree) and isinstance(tree.get("tree"), list):
        if tree.get("truncated"):
            evidence["evidence_notes"].append(
                "The warehouse file tree exceeded the upper limit of GitHub and was truncated, and some source code files failed to obtain evidence."
            )
        paths = [
            str(item["path"])
            for item in tree["tree"]
            if item.get("type") == "blob" and item.get("path")
        ][:200]
    for path in _pick_key_files(paths, limit=2):
        file_data = await client.get_file_content(owner, repo, path, ref=branch)
        if _is_error(file_data):
            continue
        content = str(file_data.get("content") or "")[:MAX_EVIDENCE_FILE_CHARS]
        evidence.setdefault("key_files", []).append({"path": path, "excerpt": content})

    if not evidence.get("summary") and not evidence.get("key_files"):
        evidence["evidence_notes"].append("The README/source code content has not been obtained, and the evidence is limited.")
    return evidence


