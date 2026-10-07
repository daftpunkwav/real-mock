"""Export one interview session as a self-contained file (report or record).

Markdown is the human-readable rendering; JSON wraps the stored payload with
session metadata for full-fidelity reuse. Phase ids are printed as stored —
the label catalog is frontend SSOT and the payloads' own text is already
locale-bound at generation time.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from realmock.domains.records.schemas.report import DebriefReport, ReportResponse
from realmock.domains.records.services.legacy_fallback import try_legacy_report
from realmock.domains.records.services.report_store import (
    STATUS_FAILED,
    STATUS_READY,
    get_report_row,
    parse_payload,
)
from realmock.platform.contracts.data_export import MIME_JSON, MIME_MARKDOWN, DataExportFile
from realmock.platform.contracts.session_catalog import (
    SessionSnapshot,
    get_session_catalog,
    snapshot_from_catalog_dict,
)
from realmock.platform.core.constants import SessionStatus
from realmock.platform.core.errors import raise_error
from realmock.platform.core.session_auth import assert_session_token

logger = logging.getLogger(__name__)


def _require_snapshot(db: Session, session_id: int, access: str | None) -> SessionSnapshot:
    """Load the session snapshot or 404; enforce the capability token.

    A malformed catalog dict maps to A2001 like the report routes do instead
    of surfacing a raw ValidationError as a 500.
    """
    raw = get_session_catalog().get_session_snapshot(db, session_id)
    if raw is None:
        raise_error("A2001")
    try:
        snap = snapshot_from_catalog_dict(raw)
    except Exception:
        logger.debug("export snapshot invalid sid=%s", session_id, exc_info=True)
        raise_error("A2001")
    assert_session_token(snap, access)
    return snap


def _require_finished_snapshot(db: Session, session_id: int, access: str | None) -> SessionSnapshot:
    """Snapshot of a completed (or ledger-frozen) session; A2003 otherwise."""
    snap = _require_snapshot(db, session_id, access)
    if snap.status != SessionStatus.COMPLETED.value and not snap.ledger_frozen:
        raise_error("A2003")
    return snap


def _meta(snap: SessionSnapshot) -> dict[str, Any]:
    """Session metadata block shared by every export variant."""
    return {
        "session_id": snap.id,
        "role": snap.role,
        "level": snap.level,
        "company": snap.company,
        "interview_style": snap.interview_style,
        "overall_score": snap.overall_score,
        "result": snap.result,
        "process_id": snap.process_id,
        "round_no": snap.round_no,
        "started_at": snap.started_at.isoformat() if snap.started_at else None,
        "ended_at": snap.ended_at.isoformat() if snap.ended_at else None,
        "created_at": snap.created_at.isoformat() if snap.created_at else None,
    }


def _load_report(db: Session, session_id: int) -> ReportResponse:
    """Ready report via the store, then the legacy session.report fallback."""
    row = get_report_row(db, session_id)
    if row is not None:
        if row.status == STATUS_FAILED:
            raise_error("A2005")
        if row.status != STATUS_READY:
            raise_error("A2004")
        report = parse_payload(row)
        if report is None:
            raise_error("A2004")
        return ReportResponse(session_id=session_id, report=report)
    legacy = try_legacy_report(db, session_id)
    if legacy is not None:
        return legacy
    raise_error("A2004")


def _bullet_list(items: list[str], indent: str = "") -> list[str]:
    """Render items as markdown bullets, flattening embedded newlines."""
    return [f"{indent}- {item.replace(chr(10), ' ')}" for item in items]


def _score_table(report: DebriefReport) -> list[str]:
    """Render the score breakdown as a markdown table."""
    b = report.score_breakdown
    rows = [
        "| Dimension | Score |",
        "| --- | --- |",
        f"| Technical | {b.technical} |",
        f"| Communication | {b.communication} |",
        f"| Project depth | {b.project_depth} |",
        f"| Problem solving | {b.problem_solving} |",
        f"| Presence | {b.presence} |",
        f"| Politeness | {b.politeness} |",
        f"| Overall | {b.overall} |",
    ]
    return rows


def _turn_note_fields_md(note: Any) -> list[str]:
    """Render one turn note's QA summary and guidance fields."""
    lines: list[str] = []
    if note.question:
        lines.append(f"**Question**: {note.question}")
    if note.question_intent:
        lines.append(f"**Intent**: {note.question_intent}")
    if note.answer_summary:
        lines.append(f"**Answer summary**: {note.answer_summary}")
    if note.score:
        lines.append(f"**Score**: {note.score}")
    for label, values in (
        ("Problems", note.problems),
        ("Knowledge points", note.knowledge_points),
        ("Exercises", note.exercises),
    ):
        if values:
            lines.append(f"**{label}**:")
            lines.extend(_bullet_list(values))
    if note.reference_answer:
        lines.append(f"**Reference answer**: {note.reference_answer}")
    if note.how_to_answer:
        lines.append(f"**How to answer**: {note.how_to_answer}")
    if note.knowledge_brushup:
        lines.append(f"**Brush-up**: {note.knowledge_brushup}")
    return lines


def _turn_notes_md(report: DebriefReport) -> list[str]:
    """Render all turn notes as one markdown subsection per turn."""
    lines: list[str] = []
    for i, note in enumerate(report.turn_notes, start=1):
        phase = f" · {note.phase}" if note.phase else ""
        lines.append(f"### Turn {i}{phase}")
        lines.append("")
        lines.extend(_turn_note_fields_md(note))
        lines.append("")
    return lines


def _report_prose_md(report: DebriefReport) -> list[str]:
    """Render named prose sections that carry content."""
    lines: list[str] = []
    prose_blocks = (
        ("Verdict reasoning", report.verdict_reasoning),
        ("Face analysis", report.face_analysis_summary),
        ("Rounds context", report.rounds_context),
    )
    for label, text in prose_blocks:
        if text.strip():
            lines.extend([f"## {label}", "", text, ""])
    return lines


def _report_lists_md(report: DebriefReport) -> list[str]:
    """Render named bullet-list sections that carry content."""
    lines: list[str] = []
    list_blocks = (
        ("Highlights", report.highlights),
        ("Key problems", report.key_problems),
        ("Strengths", report.strengths),
        ("Weaknesses", report.weaknesses),
        ("Improvement suggestions", report.improvement_suggestions),
        ("Resume suggestions", report.resume_suggestions),
        ("Interview suggestions", report.interview_suggestions),
        ("Training plan", report.training_plan),
        ("Presence moments", report.presence_moments),
        ("External notes", report.external_notes),
    )
    for label, values in list_blocks:
        if values:
            lines.extend([f"## {label}", ""])
            lines.extend(_bullet_list(values))
            lines.append("")
    return lines


def report_markdown(meta: dict[str, Any], report: DebriefReport) -> str:
    """Render the debrief report as a structured markdown document."""
    title = meta.get("role") or "Mock interview"
    company = meta.get("company") or ""
    lines = [f"# {title} — Interview Report", ""]
    if company:
        lines.append(f"**Company**: {company}")
    lines.append(f"**Overall score**: {report.overall_score}")
    if report.verdict:
        lines.append(f"**Verdict**: {report.verdict}")
    lines.append("")
    lines.extend(_score_table(report))
    lines.append("")

    lines.extend(_report_prose_md(report))
    lines.extend(_report_lists_md(report))

    if report.phase_summary:
        lines.extend(["## Phase summary", ""])
        for phase, text in report.phase_summary.items():
            lines.append(f"- **{phase}**: {text}")
        lines.append("")

    if report.turn_notes:
        lines.extend(["## Turn notes", ""])
        lines.extend(_turn_notes_md(report))

    return "\n".join(lines).rstrip() + "\n"


def build_report_export(db: Session, session_id: int, access: str | None) -> DataExportFile:
    """Markdown/JSON file for one session's debrief report."""
    snap = _require_finished_snapshot(db, session_id, access)
    response = _load_report(db, session_id)
    meta = _meta(snap)
    return DataExportFile(
        filename=f"interview-report-{session_id}.md",
        mime=MIME_MARKDOWN,
        content=report_markdown(meta, response.report),
    )


def build_report_export_json(db: Session, session_id: int, access: str | None) -> DataExportFile:
    """JSON file for one session's debrief report (full payload + session meta)."""
    snap = _require_finished_snapshot(db, session_id, access)
    response = _load_report(db, session_id)
    payload = {
        "session": _meta(snap),
        "report": response.report.model_dump(mode="json"),
    }
    return DataExportFile(
        filename=f"interview-report-{session_id}.json",
        mime=MIME_JSON,
        content=json.dumps(payload, ensure_ascii=False, indent=2),
    )


def _ledger_turns(ledger: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Collect dict-shaped turns from a ledger document (empty when absent)."""
    if not ledger:
        return []
    turns = ledger.get("turns")
    return [t for t in turns if isinstance(t, dict)] if isinstance(turns, list) else []


def _record_header_md(meta: dict[str, Any]) -> list[str]:
    """Render the transcript header block (title, company, date, scope note)."""
    title = meta.get("role") or "Mock interview"
    lines = [f"# {title} — Interview Record", ""]
    company = meta.get("company") or ""
    if company:
        lines.append(f"**Company**: {company}")
    if meta.get("created_at"):
        lines.append(f"**Date**: {meta['created_at']}")
    lines.extend(
        ["", "_(Interviewer questions and candidate replies only; no AI evaluation.)_", ""]
    )
    return lines


def _record_turn_md(index: int, turn: dict[str, Any]) -> list[str]:
    """Render one ledger turn as speaker-labelled paragraphs."""
    lines = [f"## Turn {index}", ""]
    raw_assistant = turn.get("assistant")
    assistant = raw_assistant if isinstance(raw_assistant, dict) else {}
    text = str(assistant.get("text") or "").strip()
    if text and assistant.get("visible", True):
        lines.extend(["**Interviewer**:", "", text, ""])
    raw_user = turn.get("user")
    user = raw_user if isinstance(raw_user, dict) else {}
    reply = str(user.get("text") or "").strip()
    if reply:
        lines.extend(["**Candidate**:", "", reply, ""])
    return lines


def build_record_export(db: Session, session_id: int, access: str | None) -> DataExportFile:
    """Markdown transcript: interviewer lines vs candidate replies, no AI notes."""
    snap = _require_finished_snapshot(db, session_id, access)
    ledger = get_session_catalog().get_ledger(db, session_id)
    turns = _ledger_turns(ledger)
    lines = _record_header_md(_meta(snap))
    for i, turn in enumerate(turns, start=1):
        lines.extend(_record_turn_md(i, turn))
    return DataExportFile(
        filename=f"interview-record-{session_id}.md",
        mime=MIME_MARKDOWN,
        content="\n".join(lines).rstrip() + "\n",
    )


def build_record_export_json(db: Session, session_id: int, access: str | None) -> DataExportFile:
    """JSON transcript: the ledger document wrapped with session metadata."""
    snap = _require_finished_snapshot(db, session_id, access)
    ledger = get_session_catalog().get_ledger(db, session_id)
    payload = {"session": _meta(snap), "record": {"turns": _ledger_turns(ledger)}}
    return DataExportFile(
        filename=f"interview-record-{session_id}.json",
        mime=MIME_JSON,
        content=json.dumps(payload, ensure_ascii=False, indent=2),
    )
