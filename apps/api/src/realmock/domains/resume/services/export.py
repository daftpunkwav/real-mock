"""Export one resume's deep-review analysis as a self-contained file (md / json).

Markdown is the human-readable rendering (top-level findings and drills);
JSON is the full stored payload for tooling. ``include_resume`` folds the
parsed profile into the export so the analysis travels with the resume
content it evaluated — the original binary file stays a separate download.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from realmock.domains.resume.schemas.analysis import ResumeAnalysis
from realmock.domains.resume.services import store
from realmock.domains.resume.services.analysis_normalize import normalize_resume_analysis_payload
from realmock.platform.contracts.data_export import MIME_JSON, MIME_MARKDOWN, DataExportFile
from realmock.platform.core.errors import raise_error


def _load_analysis(row: Any) -> ResumeAnalysis:
    """Parse the persisted analysis JSON or 404 when the review never ran."""
    try:
        payload = json.loads(row.analysis or "")
    except json.JSONDecodeError:
        payload = None
    if not isinstance(payload, dict) or not payload:
        raise_error("A1010")
    try:
        return ResumeAnalysis.model_validate(normalize_resume_analysis_payload(payload))
    except ValidationError as exc:
        raise_error("A1010", cause=exc)


def _resume_meta(row: Any) -> dict[str, Any]:
    """Resume identity block for the JSON envelope."""
    return {
        "id": row.id,
        "filename": row.filename,
        "file_type": row.file_type,
        "score": row.score,
        "created_at": row.created_at.isoformat() if getattr(row, "created_at", None) else None,
    }


def _md_list(label: str, items: list[str]) -> list[str]:
    lines = [f"## {label}", ""]
    lines.extend(f"- {item.replace(chr(10), ' ')}" for item in items if str(item).strip())
    lines.append("")
    return lines


def _md_interview_drills(analysis: ResumeAnalysis) -> list[str]:
    if not analysis.interview_qa:
        return []
    lines = ["## Interview drills", ""]
    for i, qa in enumerate(analysis.interview_qa, start=1):
        lines.append(f"### Q{i}. {qa.question}")
        lines.append("")
        if qa.intent:
            lines.append(f"**Intent**: {qa.intent}")
        if qa.answer_points:
            lines.append("**Answer points**:")
            lines.extend(f"- {p}" for p in qa.answer_points)
        if qa.follow_ups:
            lines.append("**Follow-ups**:")
            lines.extend(f"- {q}" for q in qa.follow_ups)
        lines.append("")
    return lines


def _md_project_cards(analysis: ResumeAnalysis) -> list[str]:
    if not analysis.project_cards:
        return []
    lines = ["## Project cards", ""]
    for card in analysis.project_cards:
        lines.extend([f"### {card.name}", ""])
        if card.one_line:
            lines.append(card.one_line)
            lines.append("")
        for label, values in (
            ("Highlights", card.highlights),
            ("Risks", card.risks),
        ):
            if values:
                lines.append(f"**{label}**:")
                lines.extend(f"- {v}" for v in values)
        if card.deep_questions:
            lines.append("**Must-ask questions**:")
            for q in card.deep_questions:
                text = q if isinstance(q, str) else (q.question or "")
                if text.strip():
                    lines.append(f"- {text}")
        lines.append("")
    return lines


def _md_resume_section(row: Any) -> list[str]:
    profile = getattr(row, "parsed_profile", None)
    try:
        profile = json.loads(profile) if isinstance(profile, str) else (profile or {})
    except json.JSONDecodeError:
        profile = {}
    lines = ["## Resume", ""]
    if not isinstance(profile, dict) or not profile:
        lines.extend(["_(Parsed profile unavailable.)_", ""])
        return lines
    lines.append(f"**Name**: {profile.get('name') or '-'}")
    if profile.get("summary"):
        lines.append(f"**Summary**: {profile['summary']}")
    lines.append("")
    skills = profile.get("skills") or []
    if skills:
        lines.append("**Skills**: " + ", ".join(str(s) for s in skills))
        lines.append("")
    projects = profile.get("projects") or []
    if projects:
        lines.append("**Projects**:")
        for p in projects:
            name = p.get("name") if isinstance(p, dict) else None
            desc = p.get("description") if isinstance(p, dict) else None
            lines.append(f"- {name or desc or '-'}")
        lines.append("")
    return lines


def analysis_markdown(row: Any, analysis: ResumeAnalysis, *, include_resume: bool) -> str:
    """Render the deep-review analysis as a structured markdown document."""
    lines = [f"# Resume Deep Review — {row.filename}", ""]
    lines.append(f"**Overall score**: {analysis.score}")
    if analysis.seniority_estimate:
        lines.append(f"**Seniority**: {analysis.seniority_estimate}")
    if analysis.headline:
        lines.append(f"**Headline**: {analysis.headline}")
    lines.append("")

    if analysis.first_impression:
        lines.extend(["## First impression", "", analysis.first_impression, ""])
    if analysis.overall_narrative:
        lines.extend(["## Overall narrative", "", analysis.overall_narrative, ""])

    if analysis.dimension_scores:
        lines.extend(["## Dimension scores", "", "| Dimension | Score |", "| --- | --- |"])
        for key, dim in analysis.dimension_scores.items():
            score = dim.score if hasattr(dim, "score") else dim
            lines.append(f"| {key} | {score} |")
        lines.append("")

    list_blocks = (
        ("Strengths", analysis.strengths),
        ("Weaknesses", analysis.weaknesses),
        ("Red flags", analysis.red_flags),
        ("Improvement suggestions", analysis.improvement_suggestions),
        ("Predicted questions", analysis.predicted_questions),
        ("Interview risk areas", analysis.interview_risk_areas),
        ("Market insights", analysis.market_insights),
    )
    for label, values in list_blocks:
        if values:
            lines.extend(_md_list(label, list(values)))

    lines.extend(_md_interview_drills(analysis))

    if analysis.project_deep_dive:
        lines.extend(_md_list("Project deep dive", list(analysis.project_deep_dive)))

    lines.extend(_md_project_cards(analysis))

    if include_resume:
        lines.extend(_md_resume_section(row))

    return "\n".join(lines).rstrip() + "\n"


def build_analysis_export(
    db: Session,
    resume_id: int,
    *,
    fmt: str,
    include_resume: bool = False,
) -> DataExportFile:
    """Markdown/JSON file for one resume's deep-review analysis."""
    row = store.get_row(db, resume_id)
    if not row:
        raise_error("A1005")
    analysis = _load_analysis(row)
    meta = _resume_meta(row)
    if fmt == "json":
        payload: dict[str, Any] = {
            "resume": meta,
            "analysis": json.loads(row.analysis or ""),
        }
        if include_resume:
            try:
                profile = json.loads(row.parsed_profile or "")
            except (json.JSONDecodeError, TypeError):
                profile = None
            payload["resume"]["parsed_profile"] = profile
        return DataExportFile(
            filename=f"resume-analysis-{resume_id}.json",
            mime=MIME_JSON,
            content=json.dumps(payload, ensure_ascii=False, indent=2),
        )
    return DataExportFile(
        filename=f"resume-analysis-{resume_id}.md",
        mime=MIME_MARKDOWN,
        content=analysis_markdown(row, analysis, include_resume=include_resume),
    )
