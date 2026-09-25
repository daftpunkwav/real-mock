"""Debrief report schemas including per-turn notes.

``TurnNote`` carries the deep per-dialogue-round analysis (reference answer,
score, problems, how to answer, knowledge points); the legacy
``user_review``/``interviewer_review`` blocks remain so payloads written
before the ReAct report agent still validate.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ReportStatus = Literal["pending", "ready", "failed", "generating"]

#: Agent-announced round verdict carried on the report for alignment.
Verdict = Literal["passed", "failed"]


class ScoreBreakdown(BaseModel):
    technical: int = 0
    communication: int = 0
    project_depth: int = 0
    problem_solving: int = 0
    presence: int = 0
    politeness: int = 0
    overall: int = 0


class TurnNoteUserReview(BaseModel):
    summary: str = ""
    suggestions: list[str] = Field(default_factory=list)


class TurnNoteInterviewerReview(BaseModel):
    intent: str = ""
    quality: str = ""
    notes: str = ""


# Deep analysis of one dialogue round (interviewer question + candidate answer).
class TurnNote(BaseModel):

    turn_id: str
    phase: str = ""
    question: str = ""
    question_intent: str = ""
    answer_summary: str = ""
    score: int = 0  # 0-100; 0 = not rated
    problems: list[str] = Field(default_factory=list)
    reference_answer: str = ""
    how_to_answer: str = ""
    knowledge_points: list[str] = Field(default_factory=list)
    # Focused brush-up on this turn's weak spots (prose, not a topic list).
    knowledge_brushup: str = ""
    # Consolidation drills for this turn (each item: prompt + solving direction).
    exercises: list[str] = Field(default_factory=list)
    followup_quality: str = ""
    # Legacy review blocks (pre-ReAct payloads); new agents leave them empty.
    user_review: TurnNoteUserReview = Field(default_factory=TurnNoteUserReview)
    interviewer_review: TurnNoteInterviewerReview = Field(
        default_factory=TurnNoteInterviewerReview
    )


# Full debrief payload stored in ``interview_reports.payload`` when ready.
class DebriefReport(BaseModel):

    overall_score: int = 0
    score_breakdown: ScoreBreakdown = Field(default_factory=ScoreBreakdown)
    verdict: str | None = None  # passed / failed; None = not judged
    verdict_reasoning: str = ""
    highlights: list[str] = Field(default_factory=list)
    key_problems: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    improvement_suggestions: list[str] = Field(default_factory=list)
    resume_suggestions: list[str] = Field(default_factory=list)
    interview_suggestions: list[str] = Field(default_factory=list)
    training_plan: list[str] = Field(default_factory=list)
    phase_summary: dict[str, str] = Field(default_factory=dict)
    face_analysis_summary: str = ""
    presence_moments: list[str] = Field(default_factory=list)
    rounds_context: str = ""  # prior-round digests when part of a process
    # External verification notes from the synthesis agent's web tools
    # (claim → finding → source URL); empty when nothing was checked.
    external_notes: list[str] = Field(default_factory=list)
    turn_notes: list[TurnNote] = Field(default_factory=list)


# GET /reports/{session_id} response shape for the frontend.
class ReportResponse(BaseModel):

    session_id: int
    report: DebriefReport
    messages_count: int = 0
    duration_minutes: float | None = None
    status: ReportStatus = "ready"
    ledger: dict[str, Any] | None = None


__all__ = [
    "DebriefReport",
    "ReportResponse",
    "ScoreBreakdown",
    "TurnNote",
    "TurnNoteInterviewerReview",
    "TurnNoteUserReview",
    "ReportStatus",
    "Verdict",
]
