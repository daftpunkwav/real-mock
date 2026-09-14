"""Review-context builders: DB-backed inputs for the resume-review Agent.

Responsibilities:
- Reference the nearest lower scored version in the family (scores are context
  for explaining change, never targets). Same-file re-reviews receive no
  historical scores and are scored from current evidence alone.

Agents must not query the store directly; they receive this block as a plain
string (see ``agents.payload.build_review_user_message``). Must not import
agents or FastAPI.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from realmock.domains.resume.services import resume_versions
from realmock.domains.resume.services.resume_mappers import load_analysis_dict
from realmock.domains.resume.services.score_anchor import calibration_text
from realmock.platform.models import Resume


def build_review_calibration(resume: Resume, db: Session) -> str:
    """Nearest lower scored version in the family, or empty.

    Same-file scores are never shown: re-reviews score strictly from the
    evidence in the current review against the dimension rubric.
    """
    previous = resume_versions.previous_scored_row(db, resume)
    if previous is None:
        return ""
    return calibration_text(
        previous_analysis=load_analysis_dict(previous.analysis, previous.id),
        previous_version_n=previous.version_n,
    )


__all__ = ["build_review_calibration"]
