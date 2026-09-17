"""Planner prompt construction (pure text; no LLM/DB access)."""

from __future__ import annotations

import json
from typing import Any

from realmock.domains.interview.schemas import InterviewConfig

PLAN_JSON_CONTRACT = """{
  "round_note": "<one line positioning of this round, in the interview language>",
  "language": "\"zh\" or \"en\" (the interview language, see rule 8)",
  "opening": {"style": "\"identity_confirm\" | \"resume_ack\" | \"casual_warmup\" (see rule 3)", "note": "<one-line personalization with concrete facts: candidate name + one resume fact>"},
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
3. Step 1 is the opening step and MUST realize the chosen opening.style (do not always pick identity_confirm — roll the dice every session, weighted by the interviewer personality: pressure/expert lean resume_ack, gentle/hr lean casual_warmup or identity_confirm, professional picks any):
   - identity_confirm: brief identity check (name + applied role), one short exchange, then into the first topic.
   - resume_ack: state you have read the resume, recap the candidate by name plus one concrete resume fact, confirm OK, and go straight into the opening topic — no identity interrogation.
   - casual_warmup: at most two sentences of warm small talk, then start.
   Keep the opening to 1-2 questions; close with a summary step where the interviewer announces the verdict.
4. Include exactly one step with "kind": "reverse_qa" where the candidate asks the interviewer questions.
5. Scale depth to the target role/level (intern vs senior), the interviewer strictness, and this round's position in the process.
6. When prior-round context is provided: avoid re-asking covered topics; go deeper or probe previously weak points; raise difficulty in later rounds.
7. "title" is a short user-visible phrase in the interview language (<= 12 CJK chars or <= 8 English words); "focus" explains what to assess.
8. Decide "language" from the signals below: default to the UI locale; when the resume/profile text is predominantly in the other language, follow the resume — the interview must run in the candidate's working language. Write "title", "focus", "round_note", and "opening.note" all in that language.
9. "max_questions" per step: 1-8 (deep dives 4-8, transitions 1-2)."""


def build_plan_user_message(
    config: InterviewConfig,
    *,
    resume_payload: dict[str, Any] | None,
    profile: Any | None,
    process_section: str,
    company_context: str,
    ui_locale: str | None = None,
) -> str:
    """Compose the planner user message from resume/profile/process context."""
    parts: list[str] = [
        f"Target role: {config.role}\nLevel: {config.level}\nCompany: {config.company}\n"
        f"Interview type: {config.workflow_type}\n"
        f"Interviewer personality: {config.personality}; strictness: {config.strictness}/10; "
        f"style: {config.interview_style}"
    ]
    # Language signals for rule 8: the planner judges the working language.
    lang_signals = f"UI locale: {ui_locale or 'unknown'}"
    preferred = (getattr(profile, "preferred_languages", "") or "").strip() if profile is not None else ""
    if preferred:
        lang_signals += f"; candidate preferred languages: {preferred}"
    lang_signals += " (the Resume block below shows which language the resume is written in)"
    parts.append(f"## Language signals\n{lang_signals}")
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
