"""Pre-interview GitHub evidence pass (facts only; never blocks the opening).

Instead of the interviewer crawling repos live while the candidate waits, a
background task right after session creation pulls a small evidence digest —
profile, top repos, one README — straight through the GitHub REST tools and
persists it on the session row. The interviewer reads it from the frozen
system head and keeps the ``github_*`` tools for at most one specific
follow-up check (see the LIVE tool-discipline rule in agent_prompts).

Failure is honest and cheap: any error leaves the column empty and the
interviewer falls back to live lookups.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from realmock.domains.interview.models import InterviewSession
from realmock.platform.capabilities.integrations.github.tools import execute_github_tool
from realmock.platform.database import api_db_session, sessions_db_session
from realmock.platform.services.candidate_read import get_user_profile

logger = logging.getLogger(__name__)

#: Hard cap on the persisted digest so the frozen system head stays bounded.
EVIDENCE_MAX_CHARS = 2400
#: Outer timeout per REST call; the GitHub client has its own 20s HTTP timeout,
#: this only guards against a hung call stalling the seeding task.
_CALL_TIMEOUT_SECONDS = 25.0
#: README excerpt per repo — enough to ground project questions, small enough
#: to keep the head cheap.
_README_CHARS = 700


async def _call(name: str, args: dict[str, Any]) -> Any:
    """One GitHub REST call with an outer timeout; None on any failure."""
    try:
        raw = await asyncio.wait_for(
            execute_github_tool(name, args), timeout=_CALL_TIMEOUT_SECONDS
        )
        data = json.loads(raw)
    except Exception:
        logger.debug("github evidence call failed name=%s", name, exc_info=True)
        return None
    if isinstance(data, dict) and data.get("error"):
        return None
    return data


def _repo_line(repo: dict[str, Any]) -> str:
    name = str(repo.get("name") or "").strip()
    if not name:
        return ""
    line = f"- {name}"
    stars = repo.get("stargazers_count")
    if isinstance(stars, int):
        line += f" stars={stars}"
    language = str(repo.get("language") or "").strip()
    if language:
        line += f" lang={language}"
    desc = str(repo.get("description") or "").strip()[:120]
    if desc:
        line += f": {desc}"
    return line


async def gather_evidence(username: str) -> str:
    """Run the bounded REST pass and render the digest ("" when nothing verifiable)."""
    parts: list[str] = []
    user = await _call("github_get_user", {"username": username})
    if not isinstance(user, dict):
        return ""
    name = str(user.get("name") or user.get("login") or username).strip()
    public_repos = user.get("public_repos")
    head = f"GitHub user: {name} (@{user.get('login') or username})"
    if isinstance(public_repos, int):
        head += f", {public_repos} public repos"
    bio = str(user.get("bio") or "").strip()[:160]
    if bio:
        head += f" — {bio}"
    parts.append(head)

    repos = await _call("github_list_repos", {"username": username, "per_page": 10})
    # github_list_repos resolves to {"username", "count", "repos": [...]}.
    repo_items = repos.get("repos") if isinstance(repos, dict) else repos
    candidates = [
        r
        for r in (repo_items if isinstance(repo_items, list) else [])
        if isinstance(r, dict) and str(r.get("name") or "").strip() and not r.get("fork")
    ]
    candidates.sort(key=lambda r: r.get("stargazers_count") or 0, reverse=True)
    top = candidates[:3]
    if not top:
        return ""
    parts.append("Top repos:")
    parts.extend(line for line in (_repo_line(r) for r in top) if line)

    readme = await _call(
        "github_get_readme", {"owner": username, "repo": str(top[0].get("name"))}
    )
    if isinstance(readme, dict):
        # Verified contract (rest_ops_repo._get_readme): the decoded text is
        # under "content"; errors carry an "error" key (filtered by _call).
        content = str(readme.get("content") or "").strip()
        if content:
            flag = " (truncated)" if readme.get("truncated") else ""
            parts.append(f"README of {top[0].get('name')}{flag}: {content[:_README_CHARS]}")
    return "\n".join(parts)[:EVIDENCE_MAX_CHARS]


async def seed_session_github_evidence(session_id: int) -> None:
    """Best-effort evidence seeding on the session row; never raises."""
    try:
        with sessions_db_session() as db:
            session = db.get(InterviewSession, session_id)
            if session is None or (session.github_evidence or "").strip():
                return
            profile_id = getattr(session, "profile_id", None)
            if not profile_id:
                return
            with api_db_session() as api_db:
                profile = get_user_profile(api_db, profile_id)
            username = (getattr(profile, "github_username", "") or "").strip() if profile else ""
            if not username:
                return
            evidence = await gather_evidence(username)
            if evidence.strip():
                session.github_evidence = evidence
                db.commit()
                logger.info(
                    "github evidence seeded sid=%s chars=%d", session_id, len(evidence)
                )
    except Exception:
        logger.debug("github evidence seed failed sid=%s", session_id, exc_info=True)


__all__ = ["EVIDENCE_MAX_CHARS", "gather_evidence", "seed_session_github_evidence"]
