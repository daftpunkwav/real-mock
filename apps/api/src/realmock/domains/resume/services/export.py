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
    """Render a labelled markdown bullet section, skipping blank items."""
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


def _md_project_card(card: Any) -> list[str]:
    """Render one project card: summary, highlights, risks, must-ask drills."""
    lines = [f"### {card.name}", ""]
    if card.one_line:
        lines.append(card.one_line)
        lines.append("")
    lines.extend(_md_card_bullets("Highlights", card.highlights))
    lines.extend(_md_card_bullets("Risks", card.risks))
    lines.extend(_md_card_questions(card.deep_questions))
    lines.append("")
    return lines


def _md_card_bullets(label: str, values: Any) -> list[str]:
    """Render a titled bullet block, or nothing when the list is empty."""
    if not values:
        return []
    lines = [f"**{label}**:"]
    lines.extend(f"- {v}" for v in values)
    return lines


def _md_card_questions(questions: Any) -> list[str]:
    """Render the must-ask drill questions, dropping blank entries."""
    if not questions:
        return []
    lines = ["**Must-ask questions**:"]
    for q in questions:
        text = q if isinstance(q, str) else (q.question or "")
        if text.strip():
            lines.append(f"- {text}")
    return lines


def _md_project_cards(analysis: ResumeAnalysis) -> list[str]:
    """Render all project deep-dive cards."""
    if not analysis.project_cards:
        return []
    lines = ["## Project cards", ""]
    for card in analysis.project_cards:
        lines.extend(_md_project_card(card))
    return lines


def _md_profile_dict(profile: dict[str, Any], *, indent: str) -> list[str]:
    """Render one level of profile keys, recursing into nested containers."""
    lines = []
    for key, item in profile.items():
        label = str(key).replace("_", " ").title()
        if isinstance(item, (dict, list)):
            lines.append(f"{indent}- **{label}**:")
            lines.extend(_md_profile_value(item, indent=indent + "  "))
        else:
            lines.append(f"{indent}- **{label}**: {item}")
    return lines


def _md_profile_list(items: list[Any], *, indent: str) -> list[str]:
    """Render list items, joining each item's own lines under one bullet."""
    lines = []
    for item in items:
        item_lines = _md_profile_value(item, indent=indent + "  ")
        if item_lines:
            lines.append(f"{indent}- {item_lines[0][len(indent) + 2 :]}")
            lines.extend(item_lines[1:])
    return lines


def _md_profile_value(value: Any, *, indent: str = "") -> list[str]:
    """Render flexible profile fields without dropping nested resume details."""
    if isinstance(value, dict):
        return _md_profile_dict(value, indent=indent)
    if isinstance(value, list):
        return _md_profile_list(list(value), indent=indent)
    return [f"{indent}{value}"]


def _md_profile_headline(profile: dict[str, Any]) -> list[str]:
    """Render the profile's name, summary, and skill line."""
    lines = [f"**Name**: {profile.get('name') or '-'}"]
    if profile.get("summary"):
        lines.append(f"**Summary**: {profile['summary']}")
    lines.append("")
    skills = profile.get("skills") or []
    if skills:
        lines.append("**Skills**: " + ", ".join(str(s) for s in skills))
        lines.append("")
    return lines


def _md_resume_section(row: Any) -> list[str]:
    """Fold the parsed resume into the export (all non-empty fields)."""
    profile = getattr(row, "parsed_profile", None)
    try:
        profile = json.loads(profile) if isinstance(profile, str) else (profile or {})
    except json.JSONDecodeError:
        profile = {}
    lines = ["## Resume", ""]
    if not isinstance(profile, dict) or not profile:
        lines.extend(["_(Parsed profile unavailable.)_", ""])
        return lines
    lines.extend(_md_profile_headline(profile))
    for key, value in profile.items():
        if key in {"name", "summary", "skills"} or not value:
            continue
        lines.append(f"**{key.replace('_', ' ').title()}**:")
        lines.extend(_md_profile_value(value))
        lines.append("")
    return lines


def _md_analysis_lists(analysis: ResumeAnalysis) -> list[str]:
    """Render the analysis's named bullet-list sections."""
    lines: list[str] = []
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
    return lines


def analysis_markdown(row: Any, analysis: ResumeAnalysis, *, include_resume: bool) -> str:
    """Render the deep-review analysis as a structured markdown document."""
    lines = [
        f"# Resume Deep Review — {row.filename}",
        "",
        f"**Overall score**: {analysis.score}",
    ]
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

    lines.extend(_md_analysis_lists(analysis))
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
