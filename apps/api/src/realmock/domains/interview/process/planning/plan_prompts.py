"""Planner prompt construction (pure text; no LLM/DB access)."""

from __future__ import annotations

import json
from typing import Any

from realmock.domains.interview.schemas import InterviewConfig

PLAN_JSON_CONTRACT = """{
  "round_note": "<one line positioning of this round>",
  "steps": [
    {"title": "<short step title in the interview language>", "focus": "<what to assess and how>", "max_questions": 3, "kind": "reverse_qa" (only on the candidate-questions step)},
    ... 8 to 30 steps total ...
  ]
}"""

_PLANNER_SYSTEM = """You are a senior interview designer. Design the flow of ONE live mock-interview round.

Output exactly one JSON object matching this contract (no markdown fences, no commentary):
{contract}

Hard rules:
1. 8 to 30 steps; every step is a themed block of Q&A, not a single question.
2. Cover the candidate's real material: each resume project gets at least one dedicated deep-dive step.
3. Open with a short identity/self-intro step; close with a summary step where the interviewer announces the verdict.
4. Include exactly one step with "kind": "reverse_qa" where the candidate asks the interviewer questions.
5. Scale depth to the target role/level (intern vs senior), the interviewer strictness, and this round's position in the process.
6. When prior-round context is provided: avoid re-asking covered topics; go deeper or probe previously weak points; raise difficulty in later rounds.
7. "title" is a short user-visible phrase (<= 12 chars in the interview language, default Chinese); "focus" explains what to assess.
8. "max_questions" per step: 1-8 (deep dives 4-8, transitions 1-2)."""


def build_plan_user_message(
    config: InterviewConfig,
    *,
    resume_payload: dict[str, Any] | None,
    profile: Any | None,
    process_section: str,
    company_context: str,
) -> str:
    """Compose the planner user message from resume/profile/process context."""
    parts: list[str] = [
        f"Target role: {config.role}\nLevel: {config.level}\nCompany: {config.company}\n"
        f"Interview type: {config.workflow_type}\n"
        f"Interviewer personality: {config.personality}; strictness: {config.strictness}/10; "
        f"style: {config.interview_style}"
    ]
    if company_context:
        parts.append(f"## Target company\n{company_context[:1200]}")

    if profile is not None:
        parts.append(
            "## Candidate profile\n"
            f"Name: {getattr(profile, 'name', '') or '—'}\n"
            f"Target role: {getattr(profile, 'target_role', '') or '—'}\n"
            f"Experience: {getattr(profile, 'experience_years', '') or '—'} years\n"
            f"Tech domains: {', '.join(getattr(profile, 'tech_domains_list', []) or []) or '—'}\n"
            f"Highlights: {(getattr(profile, 'career_highlights', '') or '—')[:400]}"
        )

    if resume_payload:
        projects = resume_payload.get("projects") or []
        skills = resume_payload.get("skills") or []
        compact_projects = [
            {
                "name": (p.get("name") or p.get("title") or "")[:60],
                "stack": (p.get("stack") or p.get("tech") or "")[:120],
                "summary": (p.get("summary") or p.get("description") or "")[:200],
            }
            for p in projects[:10]
            if isinstance(p, dict)
        ]
        parts.append(
            "## Resume\n"
            f"Skills: {json.dumps(skills[:30], ensure_ascii=False)}\n"
            f"Projects ({len(projects)} total): {json.dumps(compact_projects, ensure_ascii=False)}"
        )

    if process_section:
        parts.append(f"## Prior rounds in this process (long-term memory)\n{process_section}")

    parts.append("Design the step plan for this round now. Reply with the JSON object only.")
    return "\n\n".join(parts)


def planner_system_prompt() -> str:
    """Flow-designer system prompt with the plan JSON contract filled in."""
    return _PLANNER_SYSTEM.format(contract=PLAN_JSON_CONTRACT)


__all__ = ["build_plan_user_message", "planner_system_prompt"]
