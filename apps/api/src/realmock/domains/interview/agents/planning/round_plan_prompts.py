"""HR round-program prompt construction (pure text; no LLM/DB access).

The HR planner acts as the hiring coordinator: given the candidate, the
role, and the company, it decides how many interview rounds are warranted,
what each round IS (technical / HR / management), who interviews
(persona/style/strictness), and the pass bar per round.
"""

from __future__ import annotations

import json
from typing import Any

ROUND_PLAN_JSON_CONTRACT = """{
  "note": "<one-line rationale, e.g. '3 rounds: junior backend, single tech deep-dive + HR fit'>",
  "rounds": [
    {"kind": "<one of tech_1|tech_2|tech_deep|hr_1|hr_2|mgmt|cross>",
     "workflow_type": "<technical|hr|management>",
     "personality": "<gentle|professional|pressure|hr|expert>",
     "interview_style": "<guided|deep_dive|continuous|challenging>",
     "strictness": <1-10>,
     "label": "<short round name in the interview language>",
     "focus": "<what this round assesses>",
     "pass_criteria": "<1-2 line pass bar, candidate-visible>"},
    ... 1 or more rounds ...
  ]
}"""

_HR_PLANNER_SYSTEM = """You are a hiring coordinator (HR) arranging a mock-interview loop for one candidate.

Output exactly one JSON object matching this contract (no markdown fences, no commentary):
{contract}

Hard rules:
1. Decide the round COUNT from the role level and the candidate: intern/junior 2-3 rounds, mid 3-4, senior+ 4-5. Never exceed the given round budget.
2. "kind" must be one of the listed ids (each id maps to a fixed frontend label; unknown ids are discarded).
3. Always include at least one technical round for engineering roles and at least one HR round for fit/motivation; senior+ loops end with a cross/management round.
4. Calibrate strictness to level (intern/junior 2-4, mid 4-6, senior+ 6-8); keep the first round the gentlest.
5. "pass_criteria" is shown to the candidate: concrete, checkable, one to two lines (e.g. "Explain one resume project end-to-end with correct trade-off reasoning; basic CS answers mostly correct").
6. The pass/fail CALL is made later by each round's interviewer — you only set the bar, never prejudge the candidate.
7. "label"/"focus"/"pass_criteria" use the interview language (default Chinese)."""

_KIND_HINTS = (
    "tech_1: technical baseline (fundamentals + one resume project); "
    "tech_2: technical depth (system design, challenge probes); "
    "tech_deep: cross-check/stress deep-dive; "
    "hr_1: motivation, career plan, culture fit; "
    "hr_2: pressure handling, compensation, final fit judgement; "
    "mgmt: leadership and decision-making; "
    "cross: executive final loop (strategy, ownership)."
)


def build_round_plan_user_message(
    *,
    role: str,
    level: str,
    company: str,
    round_budget: int,
    profile: Any | None,
    resume_summary: dict[str, Any] | None,
    company_context: str,
) -> str:
    """Compose the HR planner user message (HR-view candidate snapshot)."""
    parts: list[str] = [
        f"Target role: {role}\nLevel: {level}\nCompany: {company}\n"
        f"Round budget: at most {round_budget} rounds\n\n"
        f"Round-kind vocabulary: {_KIND_HINTS}"
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

    if resume_summary:
        projects = resume_summary.get("projects") or []
        skills = resume_summary.get("skills") or []
        parts.append(
            "## Resume snapshot\n"
            f"Skills: {json.dumps(skills[:30], ensure_ascii=False)}\n"
            f"Projects: {len(projects)} total — "
            + "; ".join(
                str((p.get("name") or p.get("title") or "")[:60])
                for p in projects[:8]
                if isinstance(p, dict) and (p.get("name") or p.get("title"))
            )
        )

    parts.append("Design the round program now. Reply with the JSON object only.")
    return "\n\n".join(parts)


def hr_planner_system_prompt() -> str:
    """HR coordinator system prompt with the round-program JSON contract filled in."""
    return _HR_PLANNER_SYSTEM.format(contract=ROUND_PLAN_JSON_CONTRACT)


__all__ = ["build_round_plan_user_message", "hr_planner_system_prompt"]
