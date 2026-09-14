"""Market keyword inference from resume content.

Responsibilities:
- Infer the resume language (zh-CN vs en) for query planning
- Collect keyword tokens from parsed profile, filename, and resume body

Pure text processing: no LLM, no network, no cache. Must not import
FastAPI, ORM sessions, or LLM clients.
"""

from __future__ import annotations

import json
import logging
import re

from realmock.domains.resume.schemas.locale import infer_resume_text_locale
from realmock.platform.models import Resume

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(
    r"[A-Za-z][A-Za-z0-9+#.]{1,31}|[\u4e00-\u9fff]{2,12}"
)
_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "have",
        "has",
        "was",
        "were",
        "been",
        "will",
        "your",
        "you",
        "our",
        "their",
        "resume",
        "cv",
        "pdf",
        "docx",
        "years",
        "year",
        "work",
        "working",
        "experience",
        "experienced",
        "using",
        "including",
        "plus",
        "etc",
        "role",
        "job",
        "team",
        "senior",
        "junior",
        "about",
        "into",
        "over",
        "more",
        "than",
        "also",
        "负责",
        "熟悉",
        "以及",
        "参与",
        "完成",
        "进行",
        "相关",
        "工作",
        "项目",
        "简历",
        "精通",
        "掌握",
        "使用",
        "开发",
        "曾",
        "主导",
    }
)


def infer_resume_query_locale(r: Resume) -> str:
    """Infer zh-CN vs en from resume body, parsed JSON, then filename."""
    return infer_resume_text_locale(r.raw_text, r.parsed_profile, r.filename)


def _parsed_profile(r: Resume) -> dict:
    try:
        profile = json.loads(r.parsed_profile or "{}")
        return profile if isinstance(profile, dict) else {}
    except Exception:
        logger.debug("Failed to parse resume profile JSON for keywords", exc_info=True)
        return {}


def _push_token(seen: set[str], out: list[str], raw: str, *, limit: int) -> None:
    token = (raw or "").strip()
    if not token or len(out) >= limit:
        return
    key = token.lower()
    if key in seen or key in _STOPWORDS:
        return
    if len(token) > 48:
        token = token[:48]
    seen.add(key)
    out.append(token)


def infer_search_keywords(r: Resume, *, limit: int = 8) -> list[str]:
    """Collect keyword tokens for retrieval. Empty when the resume has no usable terms."""
    profile = _parsed_profile(r)
    seen: set[str] = set()
    out: list[str] = []

    for key in ("target_role", "desired_role", "role"):
        val = profile.get(key)
        if isinstance(val, str) and val.strip():
            _push_token(seen, out, val.strip(), limit=limit)

    skills = profile.get("skills") or []
    if isinstance(skills, list):
        for skill in skills:
            _push_token(seen, out, str(skill), limit=limit)

    for project in profile.get("projects") or []:
        if len(out) >= limit:
            break
        if isinstance(project, dict):
            _push_token(seen, out, str(project.get("name") or ""), limit=limit)
            stack = project.get("tech_stack")
            if isinstance(stack, str):
                for part in re.split(r"[,/|;，、\s]+", stack):
                    _push_token(seen, out, part, limit=limit)
            elif isinstance(stack, list):
                for part in stack:
                    _push_token(seen, out, str(part), limit=limit)

    summary = profile.get("summary")
    if isinstance(summary, str):
        for token in _TOKEN_RE.findall(summary):
            _push_token(seen, out, token, limit=limit)

    name = (r.filename or "").rsplit(".", 1)[0]
    for part in re.split(r"[_\-\s]+", name):
        _push_token(seen, out, part, limit=limit)

    if len(out) < limit:
        for token in _TOKEN_RE.findall((r.raw_text or "")[:4000]):
            _push_token(seen, out, token, limit=limit)
            if len(out) >= limit:
                break
    return out


def infer_target_role_from_resume(r: Resume) -> str:
    """Best-effort role string from explicit fields, else joined keywords. Never a canned title."""
    profile = _parsed_profile(r)
    for key in ("target_role", "desired_role", "role"):
        val = profile.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    keywords = infer_search_keywords(r)
    return " ".join(keywords[:4])


__all__ = [
    "infer_resume_query_locale",
    "infer_search_keywords",
    "infer_target_role_from_resume",
]
