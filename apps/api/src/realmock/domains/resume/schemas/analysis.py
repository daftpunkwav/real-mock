"""Nested models for a persisted / returned resume deep-review payload.

Responsibilities:
- Declare ``ResumeAnalysis`` and its nested cards (dimensions, rewrite, repos)

List/detail HTTP still returns ``analysis`` as a dict so a dirty JSON blob
degrades to ``{}`` instead of 500. The analyze endpoint validates this model.
Must not import FastAPI or ORM.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# Single dimension score for a resume review.
class DimensionScore(BaseModel):

    score: int = Field(ge=0, le=100)
    comment: str = ""


# Before/after rewrite pair for a resume bullet.
class RewriteExample(BaseModel):

    before: str = ""
    after: str = ""


# Per-section review (education / work / projects / skills / layout).
class SectionReview(BaseModel):

    section: str = ""
    score: int = Field(ge=0, le=100)
    verdict: str = ""
    detail: str = ""


# One predicted interview question with the interviewer's intent and a model answer.
class InterviewQa(BaseModel):

    question: str = ""
    intent: str = ""
    answer_points: list[str] = Field(default_factory=list)
    follow_ups: list[str] = Field(default_factory=list)


# Deep-dive card for one project.
class ProjectCard(BaseModel):

    name: str = ""
    score: int = Field(ge=0, le=100)
    one_line: str = ""
    highlights: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    deep_questions: list[InterviewQa] = Field(default_factory=list)


# Three-tier skill trust: evidenced / claimed-only / missing for target role.
class SkillTrust(BaseModel):

    solid: list[str] = Field(default_factory=list)
    claimed: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)


# Career trajectory analysis.
class CareerAnalysis(BaseModel):

    trajectory: str = ""
    stability_score: int = Field(ge=0, le=100)
    gaps: list[str] = Field(default_factory=list)
    notes: str = ""


# Fit score for a company tier.
class CompanyFit(BaseModel):

    tier: str = ""
    fit_score: int = Field(ge=0, le=100)
    reason: str = ""


# GitHub repo evidence: metadata plus commit/source observations.
class RepoEvidence(BaseModel):

    repo: str = ""
    url: str = ""
    stars: int | None = None
    forks: int | None = None
    language: str = ""
    last_push: str = ""
    description: str = ""
    summary: str = ""
    evidence_notes: list[str] = Field(default_factory=list)


# Cross-check of resume claims against repository facts.
class RepoVerification(BaseModel):

    repo: str = ""
    verdict: str = ""
    details: str = ""


# Multi-dimension resume Agent review result.
#
# Keeps legacy strengths/weaknesses/… fields and extends with dimension_scores etc.
class ResumeAnalysis(BaseModel):

    score: int = Field(ge=0, le=100)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    improvement_suggestions: list[str] = Field(default_factory=list)
    predicted_questions: list[str] = Field(default_factory=list)
    interview_qa: list[InterviewQa] = Field(default_factory=list)
    dimension_scores: dict[str, DimensionScore] = Field(default_factory=dict)
    # Applied per-dimension weights (model-adjusted within the catalog range,
    # validated by normalize; empty for payloads written before weights).
    dimension_weights: dict[str, float] = Field(default_factory=dict)
    ats_keywords: list[str] = Field(default_factory=list)
    missing_keywords: list[str] = Field(default_factory=list)
    project_deep_dive: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    role_fit_summary: str = ""
    seniority_estimate: str = ""
    rewrite_examples: list[RewriteExample] = Field(default_factory=list)
    interview_risk_areas: list[str] = Field(default_factory=list)
    overall_narrative: str = ""
    layout_review: str = ""
    typography_review: str = ""
    content_review: str = ""
    market_insights: list[str] = Field(default_factory=list)
    search_queries_used: list[str] = Field(default_factory=list)
    headline: str = ""
    first_impression: str = ""
    interviewer_comments: list[str] = Field(default_factory=list)
    benchmark_percentile: int | None = Field(default=None, ge=0, le=100)
    section_reviews: list[SectionReview] = Field(default_factory=list)
    project_cards: list[ProjectCard] = Field(default_factory=list)
    skill_trust: SkillTrust | None = None
    career_analysis: CareerAnalysis | None = None
    company_fit: list[CompanyFit] = Field(default_factory=list)
    salary_positioning: str = ""
    repo_evidence: list[RepoEvidence] = Field(default_factory=list)
    repo_verification: list[RepoVerification] = Field(default_factory=list)
