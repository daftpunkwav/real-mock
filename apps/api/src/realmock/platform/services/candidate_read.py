"""Candidate profile / resume read façade.

Business services (agent / interview) must read ``UserProfile`` / ``Resume``
through this module instead of importing platform models directly.
Write paths stay in profile/resume/settings domains or explicit write services.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from realmock.platform.schemas import CandidateProfile

logger = logging.getLogger(__name__)

# Prep profile-summary fields (aligned with prep context)
_PROFILE_SUMMARY_FIELDS: list[tuple[str, str]] = [
    ("name", "Name"),
    ("identity", "Identity"),
    ("school", "School"),
    ("major", "Major"),
    ("education_level", "Education"),
    ("graduation_year", "Graduation year"),
    ("job_direction", "Job direction"),
    ("target_role", "Target role"),
    ("experience_years", "Years of experience"),
    ("current_company", "Current company"),
    ("tech_domains", "Tech stack"),
    ("strengths", "Self-rated strengths"),
    ("weaknesses", "Self-rated gaps"),
    ("career_highlights", "Career highlights"),
    ("signature_projects", "Signature projects"),
    ("certificates", "Certificates"),
    ("english_level", "English level"),
    ("expected_city", "Preferred city"),
]


def _safe_orm_query(db: Session, loader, *, table_label: str):
    """Return None when the target table is missing (fresh/partial DBs, tests)."""
    try:
        return loader()
    except OperationalError:
        logger.debug("%s query skipped: table unavailable", table_label, exc_info=True)
        try:
            db.rollback()
        except Exception:
            logger.debug("Rollback after missing %s failed", table_label, exc_info=True)
        return None


def get_user_profile(db: Session, profile_id: int) -> Any | None:
    """Load user profile ORM by id (for prompt builders that need all fields)."""
    from realmock.platform.models import UserProfile

    return _safe_orm_query(
        db,
        lambda: db.query(UserProfile).filter(UserProfile.id == profile_id).first(),
        table_label="UserProfile",
    )


def get_default_user_profile(db: Session) -> Any | None:
    """Load default profile: prefer id=1, else first row by ascending id."""
    from realmock.platform.models import UserProfile

    def _load():
        row = db.query(UserProfile).filter(UserProfile.id == 1).first()
        if row is None:
            row = db.query(UserProfile).order_by(UserProfile.id).first()
        return row

    return _safe_orm_query(db, _load, table_label="UserProfile")


def format_profile_summary(db: Session, profile_id: int | None = None) -> str:
    """Profile summary text (Prep / prompt injection)."""
    profile = (
        get_user_profile(db, profile_id)
        if profile_id is not None
        else get_default_user_profile(db)
    )
    if profile is None:
        return ""
    lines: list[str] = []
    for key, label in _PROFILE_SUMMARY_FIELDS:
        value = getattr(profile, key, "")
        if key == "tech_domains":
            domains = profile.tech_domains_list
            value = ", ".join(domains) if domains else ""
        value = str(value or "").strip()
        if value:
            lines.append(f"{label}: {value[:80]}")
    if not lines:
        return ""
    return "Candidate profile:\n" + "\n".join(lines[:18])


def format_resume_summary(db: Session, resume_id: int | None, *, max_chars: int = 3000) -> str:
    """Resume filename + parsed JSON summary."""
    if not resume_id:
        return ""
    from realmock.platform.models import Resume

    row = _safe_orm_query(
        db,
        lambda: db.query(Resume).filter(Resume.id == resume_id).first(),
        table_label="Resume",
    )
    if not row:
        return ""
    body = (row.parsed_profile or "")[:max_chars]
    return f"Resume: {row.filename}\n{body}"


def get_candidate_profile(db: Session, resume_id: int | None) -> CandidateProfile | None:
    """Build ``CandidateProfile`` from resume parsed JSON."""
    if not resume_id:
        return None
    from realmock.platform.models import Resume

    row = _safe_orm_query(
        db,
        lambda: db.query(Resume).filter(Resume.id == resume_id).first(),
        table_label="Resume",
    )
    if not row:
        return None
    try:
        return CandidateProfile(**json.loads(row.parsed_profile or "{}"))
    except (json.JSONDecodeError, TypeError, ValueError):
        logger.debug("Invalid resume parsed_profile JSON resume_id=%s", resume_id)
        return None


def get_resume_detail(db: Session, resume_id: int) -> tuple[str, dict[str, Any]] | None:
    """Return (filename, parsed_profile dict)."""
    from realmock.platform.models import Resume

    row = _safe_orm_query(
        db,
        lambda: db.query(Resume).filter(Resume.id == resume_id).first(),
        table_label="Resume",
    )
    if not row:
        return None
    try:
        payload = json.loads(row.parsed_profile or "{}")
        if not isinstance(payload, dict):
            payload = {}
    except (json.JSONDecodeError, TypeError):
        payload = {}
    return row.filename, payload


def get_resume_agent_payload(db: Session, resume_id: int | None) -> dict[str, Any] | None:
    """Plain resume dict for shared Agent tools (no domain imports)."""
    if not resume_id:
        return None
    from realmock.platform.models import Resume

    row = _safe_orm_query(
        db,
        lambda: db.query(Resume).filter(Resume.id == resume_id).first(),
        table_label="Resume",
    )
    if not row:
        return None
    try:
        parsed = json.loads(row.parsed_profile or "{}")
        if not isinstance(parsed, dict):
            parsed = {}
    except (json.JSONDecodeError, TypeError):
        parsed = {}
    return {
        "resume_id": int(row.id or 0),
        "filename": row.filename or "",
        "file_type": row.file_type or "",
        "raw_text": row.raw_text or "",
        "parsed": parsed,
        "layout_notes": str(parsed.get("layout_notes") or ""),
    }


def get_latest_scored_resume_id(db: Session) -> int | None:
    """Id of the newest active scored resume, else the newest scored one.

    Growth-context read port: callers only need the id and pass it back into
    the other resume readers here. Returns None when no scored resume exists
    or the table is unavailable.
    """
    from realmock.platform.models import Resume

    def _load():
        active = (
            db.query(Resume)
            .filter(Resume.is_active.is_(True), Resume.score.isnot(None))
            .order_by(Resume.id.desc())
            .first()
        )
        if active is not None:
            return active
        return (
            db.query(Resume)
            .filter(Resume.score.isnot(None))
            .order_by(Resume.created_at.desc(), Resume.id.desc())
            .first()
        )

    row = _safe_orm_query(db, _load, table_label="Resume(scored)")
    return int(row.id) if row is not None else None


def format_resume_analysis_summary(db: Session, *, max_chars: int = 2000) -> str:
    """Deep-review summary of the latest scored resume (growth context).

    Prefers the active resume; falls back to the most recent row carrying a
    non-empty ``analysis`` JSON. Emits a compact digest (score, dimension
    scores, weaknesses, missing keywords, narrative head) — no layout prose.
    Empty string when no scored resume exists.
    """
    from realmock.platform.models import Resume

    def _load():
        active = (
            db.query(Resume)
            .filter(Resume.is_active.is_(True), Resume.score.isnot(None))
            .order_by(Resume.id.desc())
            .first()
        )
        if active is not None:
            return active
        rows = (
            db.query(Resume)
            .filter(Resume.score.isnot(None))
            .order_by(Resume.created_at.desc(), Resume.id.desc())
            .limit(5)
            .all()
        )
        return next((r for r in rows if (r.analysis or "").strip()), None)

    row = _safe_orm_query(db, _load, table_label="Resume(analysis)")
    if row is None or not (row.analysis or "").strip():
        return ""
    try:
        data = json.loads(row.analysis)
    except (json.JSONDecodeError, TypeError):
        logger.debug("Invalid resume analysis JSON resume_id=%s", row.id)
        return ""
    if not isinstance(data, dict):
        return ""

    lines: list[str] = [f"Latest resume: {row.filename or '(unnamed)'} (score {row.score})"]
    dims = data.get("dimension_scores")
    if isinstance(dims, dict) and dims:
        rendered = []
        for key, value in list(dims.items())[:12]:
            score = value.get("score") if isinstance(value, dict) else value
            rendered.append(f"{key} {score}")
        lines.append("Resume dimension scores: " + ", ".join(str(x) for x in rendered))
    for field, label in (
        ("weaknesses", "Resume weaknesses"),
        ("missing_keywords", "Resume missing keywords"),
        ("red_flags", "Resume red flags"),
    ):
        values = data.get(field)
        if isinstance(values, list) and values:
            items = [str(v).strip() for v in values[:5] if str(v).strip()]
            if items:
                lines.append(f"{label}: " + "; ".join(items))
    narrative = str(data.get("overall_narrative") or "").strip()
    if narrative:
        lines.append("Resume review narrative: " + narrative[:600])
    return "\n".join(lines)[:max_chars]


__all__ = [
    "format_profile_summary",
    "format_resume_analysis_summary",
    "format_resume_summary",
    "get_candidate_profile",
    "get_default_user_profile",
    "get_latest_scored_resume_id",
    "get_resume_agent_payload",
    "get_resume_detail",
    "get_user_profile",
]
