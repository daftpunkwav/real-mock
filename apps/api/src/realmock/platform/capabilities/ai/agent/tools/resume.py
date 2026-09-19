"""Reusable resume-inspection tools for Agents.

Progressive disclosure:
- ``resume_overview`` — identity, available sections, project names, skills
- ``resume_get_section`` — one structured section or a paged raw excerpt

Callers pass a ``ResumeSnapshot``. Must not import FastAPI.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from realmock.platform.capabilities.ai.agent.tools.spec import ToolSpec

RESUME_SECTION_ORDER: tuple[str, ...] = (
    "education",
    "work",
    "projects",
    "skills",
    "summary",
    "links",
    "raw",
)

RESUME_RAW_PAGE_CHARS = 4_000
RESUME_RAW_PAGE_HARD_CHARS = 8_000
RESUME_OVERVIEW_SKILL_MAX = 24
RESUME_OVERVIEW_PROJECT_MAX = 12

_GITHUB_URL_RE = re.compile(
    r"https?://github\.com/([A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)/([A-Za-z0-9._-]+)",
    re.I,
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d[- ]?\d{4}[- ]?\d{4}(?!\d)")


def _github_urls_from_text(raw_text: str, *, limit: int = 8) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for owner, repo in _GITHUB_URL_RE.findall(raw_text or ""):
        repo = repo.removesuffix(".git")
        key = f"{owner.lower()}/{repo.lower()}"
        if key in seen:
            continue
        seen.add(key)
        urls.append(f"https://github.com/{owner}/{repo}")
        if len(urls) >= limit:
            break
    return urls


@dataclass
class ResumeSnapshot:
    """Plain resume payload shared by prep / interview / resume review."""

    resume_id: int
    filename: str
    file_type: str
    raw_text: str = ""
    parsed: dict[str, Any] = field(default_factory=dict)
    layout_notes: str = ""
    has_visual_pages: bool = False
    # Vision outcome set by the review first-message builder: "ok" |
    # "no_vision" | "missing_file" | "render_failed" | "filtered".
    visual_status: str = "ok"


def snapshot_from_payload(
    payload: dict[str, Any],
    *,
    has_visual_pages: bool = False,
) -> ResumeSnapshot:
    """Build a snapshot from a plain dict (API/ORM façades, not domain imports)."""
    raw_parsed = payload.get("parsed")
    parsed = raw_parsed if isinstance(raw_parsed, dict) else {}
    layout = str(payload.get("layout_notes") or parsed.get("layout_notes") or "")
    return ResumeSnapshot(
        resume_id=int(payload.get("resume_id") or 0),
        filename=str(payload.get("filename") or ""),
        file_type=str(payload.get("file_type") or ""),
        raw_text=str(payload.get("raw_text") or ""),
        parsed=parsed,
        layout_notes=layout,
        has_visual_pages=has_visual_pages,
    )


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _project_names(parsed: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for item in _as_list(parsed.get("projects")):
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if name:
                names.append(name)
        elif item:
            names.append(str(item).strip())
    return names[:RESUME_OVERVIEW_PROJECT_MAX]


def _skill_labels(parsed: dict[str, Any]) -> list[str]:
    skills = _as_list(parsed.get("skills"))
    out: list[str] = []
    for item in skills:
        label = str(item).strip()
        if label:
            out.append(label)
        if len(out) >= RESUME_OVERVIEW_SKILL_MAX:
            break
    return out


def _contact_bundle(parsed: dict[str, Any], raw_text: str) -> dict[str, Any]:
    """Contact facts from parsed fields, falling back to raw-text extraction.

    Reviewers judge contact completeness against this block, so a parse gap
    must not read as a missing resume section.
    """
    text = raw_text or ""
    email = str(parsed.get("email") or "").strip()
    if not email:
        match = _EMAIL_RE.search(text)
        email = match.group(0) if match else ""
    phone = str(parsed.get("phone") or "").strip()
    if not phone:
        match = _PHONE_RE.search(text)
        phone = match.group(0) if match else ""
    return {
        "email": email,
        "phone": phone,
        "city": str(parsed.get("city") or "").strip(),
    }


def _link_bundle(parsed: dict[str, Any], raw_text: str) -> dict[str, Any]:
    github = [str(u) for u in (parsed.get("github_urls") or []) if str(u).strip()]
    links = [str(u) for u in (parsed.get("links") or []) if str(u).strip()]
    if not github:
        github = _github_urls_from_text(raw_text)
    return {
        "github_urls": github,
        "links": links,
        **_contact_bundle(parsed, raw_text),
        "target_role": parsed.get("target_role") or "",
    }


def resume_tool_specs(snapshot: ResumeSnapshot) -> list[ToolSpec]:
    """Bind resume inspection tools to one snapshot."""

    async def overview(args: dict[str, Any]) -> str:
        del args
        parsed = snapshot.parsed if isinstance(snapshot.parsed, dict) else {}
        education = _as_list(parsed.get("education"))
        work = _as_list(parsed.get("work_experience"))
        projects = _as_list(parsed.get("projects"))
        payload = {
            "resume_id": snapshot.resume_id,
            "filename": snapshot.filename,
            "file_type": snapshot.file_type,
            "name": parsed.get("name") or "",
            "target_role": parsed.get("target_role") or "",
            "parse_degraded": bool(parsed.get("parse_degraded")),
            "has_visual_pages": snapshot.has_visual_pages,
            "layout_notes": (snapshot.layout_notes or "")[:400],
            "available_sections": [
                {
                    "id": "education",
                    "filled": bool(education),
                    "count": len(education),
                },
                {"id": "work", "filled": bool(work), "count": len(work)},
                {"id": "projects", "filled": bool(projects), "count": len(projects)},
                {"id": "skills", "filled": bool(_skill_labels(parsed)), "count": len(_skill_labels(parsed))},
                {"id": "summary", "filled": bool(str(parsed.get("summary") or "").strip())},
                {"id": "links", "filled": bool(_link_bundle(parsed, snapshot.raw_text)["github_urls"])},
                {"id": "raw", "filled": bool(snapshot.raw_text.strip()), "chars": len(snapshot.raw_text)},
            ],
            "project_names": _project_names(parsed),
            "skills": _skill_labels(parsed),
            "contact": _contact_bundle(parsed, snapshot.raw_text),
        }
        return json.dumps(payload, ensure_ascii=False)

    async def get_section(args: dict[str, Any]) -> str:
        section = str(args.get("section") or "").strip()
        parsed = snapshot.parsed if isinstance(snapshot.parsed, dict) else {}
        if section not in RESUME_SECTION_ORDER:
            return json.dumps(
                {"error": "unknown_section", "allowed": list(RESUME_SECTION_ORDER)},
                ensure_ascii=False,
            )
        if section == "education":
            body: Any = _as_list(parsed.get("education"))
        elif section == "work":
            body = _as_list(parsed.get("work_experience"))
        elif section == "projects":
            focus = str(args.get("focus") or "").strip().lower()
            projects = _as_list(parsed.get("projects"))
            if focus:
                projects = [
                    p
                    for p in projects
                    if focus in json.dumps(p, ensure_ascii=False).lower()
                ]
            body = projects
        elif section == "skills":
            body = {
                "skills": _skill_labels(parsed),
                "languages": list(parsed.get("languages") or []),
                "awards": list(parsed.get("awards") or []),
                "publications": list(parsed.get("publications") or []),
            }
        elif section == "summary":
            body = {
                "summary": parsed.get("summary") or "",
                "name": parsed.get("name") or "",
                "target_role": parsed.get("target_role") or "",
                "city": parsed.get("city") or "",
            }
        elif section == "links":
            body = _link_bundle(parsed, snapshot.raw_text)
        else:
            # Same tolerance as limit below: a model-supplied non-numeric
            # offset must degrade to page start, not fail the whole tool call.
            try:
                offset = int(args.get("offset") or 0)
            except (TypeError, ValueError):
                offset = 0
            offset = max(0, offset)
            try:
                limit = int(args.get("limit") or RESUME_RAW_PAGE_CHARS)
            except (TypeError, ValueError):
                limit = RESUME_RAW_PAGE_CHARS
            limit = max(200, min(limit, RESUME_RAW_PAGE_HARD_CHARS))
            text = snapshot.raw_text or ""
            chunk = text[offset : offset + limit]
            body = {
                "offset": offset,
                "limit": limit,
                "total_chars": len(text),
                "eof": offset + len(chunk) >= len(text),
                "text": chunk,
            }
        return json.dumps({"section": section, "data": body}, ensure_ascii=False)

    return [
        ToolSpec(
            name="resume_overview",
            description=(
                "Compact resume map: filename, name, skills, project names, and which "
                "sections have data. Call this before resume_get_section. Does not "
                "return full project write-ups or the raw body."
            ),
            parameters={"type": "object", "properties": {}, "required": []},
            handler=overview,
        ),
        ToolSpec(
            name="resume_get_section",
            description=(
                "Read one resume section: education, work, projects, skills, summary, "
                "links, or raw (paged). For projects, optional focus filters by keyword. "
                "For raw, use offset/limit instead of requesting the entire text."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "section": {
                        "type": "string",
                        "enum": list(RESUME_SECTION_ORDER),
                    },
                    "focus": {
                        "type": "string",
                        "description": "Optional keyword filter for the projects section",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Raw-text start character (raw section only)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Raw-text page size in characters (raw section only)",
                    },
                },
                "required": ["section"],
            },
            handler=get_section,
        ),
    ]


__all__ = [
    "RESUME_SECTION_ORDER",
    "ResumeSnapshot",
    "_contact_bundle",
    "_github_urls_from_text",
    "resume_tool_specs",
    "snapshot_from_payload",
]
