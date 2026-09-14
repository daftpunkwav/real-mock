"""Tolerant normalization of raw report-agent JSON into schema types.

The report agents are ground truth for structure but sloppy about types and
key names; this module coerces field-by-field (aliases, clamps, list caps)
so one drifted field never invalidates a whole report.
"""

from __future__ import annotations

from typing import Any

from realmock.domains.records.schemas.report import (
    DebriefReport,
    ScoreBreakdown,
    TurnNote,
    TurnNoteInterviewerReview,
    TurnNoteUserReview,
)

_NOTE_LIST_CAPS = {
    "problems": 6,
    "knowledge_points": 8,
    "exercises": 4,
}
_TOP_LIST_CAP = 10


def _clip_list_str(value: Any, cap: int) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value[:cap]:
        text = str(item or "").strip()
        if text:
            out.append(text[:400])
    return out


def _norm_score(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        score = int(float(value))
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, score))


def _norm_verdict(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if text in ("passed", "pass", "通过", "yes"):
        return "passed"
    if text in ("failed", "fail", "未通过", "no"):
        return "failed"
    return None


_NOTE_ALIASES = {
    "question": ("question", "面试官问题", "题目"),
    "question_intent": ("question_intent", "intent", "考察意图", "提问意图"),
    "answer_summary": ("answer_summary", "answer", "summary", "回答摘要"),
    "reference_answer": ("reference_answer", "reference", "参考答案"),
    "how_to_answer": ("how_to_answer", "how_to_improve", "答题思路", "该如何回答"),
    "knowledge_brushup": ("knowledge_brushup", "brushup", "知识巩固", "知识精讲", "查漏补缺"),
    "followup_quality": ("followup_quality", "followup", "追问表现"),
    "phase": ("phase", "stage", "阶段"),
}


def _alias_get(raw: dict[str, Any], key: str) -> Any:
    for name in _NOTE_ALIASES.get(key, (key,)):
        if raw.get(name) not in (None, ""):
            return raw[name]
    return None


def normalize_turn_note(raw: object) -> TurnNote | None:
    """Coerce one raw note dict into a TurnNote; None when unusable."""
    if not isinstance(raw, dict):
        return None
    turn_id = str(raw.get("turn_id") or "").strip()
    if not turn_id:
        return None
    note = TurnNote(
        turn_id=turn_id,
        phase=str(_alias_get(raw, "phase") or "").strip()[:60],
        question=str(_alias_get(raw, "question") or "").strip()[:800],
        question_intent=str(_alias_get(raw, "question_intent") or "").strip()[:400],
        answer_summary=str(_alias_get(raw, "answer_summary") or "").strip()[:1200],
        score=_norm_score(raw.get("score")),
        problems=_clip_list_str(raw.get("problems"), _NOTE_LIST_CAPS["problems"]),
        reference_answer=str(_alias_get(raw, "reference_answer") or "").strip()[:2000],
        how_to_answer=str(_alias_get(raw, "how_to_answer") or "").strip()[:800],
        knowledge_points=_clip_list_str(
            raw.get("knowledge_points"), _NOTE_LIST_CAPS["knowledge_points"]
        ),
        knowledge_brushup=str(_alias_get(raw, "knowledge_brushup") or "").strip()[:800],
        exercises=_clip_list_str(raw.get("exercises"), _NOTE_LIST_CAPS["exercises"]),
        followup_quality=str(_alias_get(raw, "followup_quality") or "").strip()[:400],
    )
    if isinstance(raw.get("user_review"), dict):
        review = raw["user_review"]
        note.user_review = TurnNoteUserReview(
            summary=str(review.get("summary") or "").strip()[:800],
            suggestions=_clip_list_str(review.get("suggestions"), 4),
        )
    if isinstance(raw.get("interviewer_review"), dict):
        review = raw["interviewer_review"]
        note.interviewer_review = TurnNoteInterviewerReview(
            intent=str(review.get("intent") or "").strip()[:400],
            quality=str(review.get("quality") or "").strip()[:40],
            notes=str(review.get("notes") or "").strip()[:400],
        )
    return note


def _norm_phase_summary(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for key, text in list(value.items())[:20]:
        clean = str(text or "").strip()[:300]
        if clean:
            out[str(key)[:60]] = clean
    return out


def normalize_report_payload(data: dict[str, Any]) -> DebriefReport:
    """Coerce the raw synthesis payload (with merged notes) into DebriefReport."""
    breakdown = ScoreBreakdown()
    breakdown_raw = data.get("score_breakdown")
    if isinstance(breakdown_raw, dict):
        for field_name in ScoreBreakdown.model_fields:
            setattr(breakdown, field_name, _norm_score(breakdown_raw.get(field_name)))

    notes: list[TurnNote] = []
    seen: set[str] = set()
    for raw in data.get("turn_notes") or []:
        note = normalize_turn_note(raw)
        if note is not None and note.turn_id not in seen:
            seen.add(note.turn_id)
            notes.append(note)

    return DebriefReport(
        overall_score=_norm_score(data.get("overall_score")),
        score_breakdown=breakdown,
        verdict=_norm_verdict(data.get("verdict")),
        verdict_reasoning=str(data.get("verdict_reasoning") or "").strip()[:1200],
        highlights=_clip_list_str(data.get("highlights"), _TOP_LIST_CAP),
        key_problems=_clip_list_str(data.get("key_problems"), _TOP_LIST_CAP),
        strengths=_clip_list_str(data.get("strengths"), _TOP_LIST_CAP),
        weaknesses=_clip_list_str(data.get("weaknesses"), _TOP_LIST_CAP),
        improvement_suggestions=_clip_list_str(data.get("improvement_suggestions"), _TOP_LIST_CAP),
        resume_suggestions=_clip_list_str(data.get("resume_suggestions"), _TOP_LIST_CAP),
        interview_suggestions=_clip_list_str(data.get("interview_suggestions"), _TOP_LIST_CAP),
        training_plan=_clip_list_str(data.get("training_plan"), _TOP_LIST_CAP),
        phase_summary=_norm_phase_summary(data.get("phase_summary")),
        face_analysis_summary=str(data.get("face_analysis_summary") or "").strip()[:600],
        presence_moments=_clip_list_str(data.get("presence_moments"), _TOP_LIST_CAP),
        rounds_context=str(data.get("rounds_context") or "").strip()[:2000],
        external_notes=_clip_list_str(data.get("external_notes"), 6),
        turn_notes=notes,
    )


__all__ = ["normalize_report_payload", "normalize_turn_note"]
