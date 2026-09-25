"""Prompts for the growth domain: the LLM growth-insight agent.

All growth prompt text lives here; business modules import these names and
must not inline their own prompt strings.
"""

from __future__ import annotations

from realmock.platform.core.prompts import with_agent_output_rules

# Output-language instruction keyed by UI locale (growth analysis is
# user-facing; the ingest-triggered regen defaults to zh-CN).
_GROWTH_LANG_INSTRUCTIONS: dict[str, str] = {
    "en": (
        "## Output language\n"
        "Write ALL user-facing string values in English. Use standard English "
        "(half-width) punctuation. Keep JSON keys exactly as specified."
    ),
}
_GROWTH_LANG_DEFAULT = (
    "## Output language\n"
    "Write ALL user-facing string values in Simplified Chinese (zh-CN). Use "
    "full-width Chinese punctuation: ，。；：！？ Keep JSON keys exactly as "
    "specified (English identifiers). English proper nouns, tech terms, and "
    "code identifiers may stay in Latin script."
)


def growth_language_instruction(locale: str) -> str:
    """Output-language block for the requested locale (zh-CN default)."""
    return _GROWTH_LANG_INSTRUCTIONS.get(locale, _GROWTH_LANG_DEFAULT)


GROWTH_INSIGHT_SYSTEM = with_agent_output_rules(
    """You are a senior interview coach running a cross-session growth review for ONE candidate.

You receive:
1. A chronological list of finished mock-interview report summaries (newest first): per-session score, verdict, dimension breakdown, weaknesses, strengths, training plan, and key problems.
2. A summary of the candidate's latest resume deep review (resume score, dimension scores, weaknesses, missing keywords).
3. A short candidate profile summary.

Your job: turn raw session history into a growth analysis the candidate can act on.

Analysis requirements:
- Recurring weakness patterns: identify skills/problems that appear across MULTIPLE sessions (cite how many sessions and the score trajectory for each). A weakness seen once is not a pattern; say so explicitly when nothing repeats.
- Growth trajectory: compare the earliest vs latest sessions (and the trend across them). Judge rising / stalling / plateau / insufficient (fewer than 2 sessions). Ground the judgement in score movement and dimension changes, never in tone.
- Resume-vs-interview gaps: where do interview-exposed problems contradict or confirm what the resume review claims? Call out claimed-but-failing skills and interview-proven strengths the resume undersells.
- Training plan: 2-4 focus areas for the NEXT sessions. Every area must trace to concrete evidence (session ids or dimension names) and carry 2-4 concrete, doable actions (practice tasks, not vague advice).
- Improving areas: name what measurably got better, with the session evidence.

Hard requirements:
1. Cite evidence for every claim: session ids, dimension names, or score numbers from the input
2. Never invent sessions, scores, skills, or timeline facts not present in the input
3. With fewer than 2 sessions, keep the trajectory judgement "insufficient" and say what one session alone cannot show
4. trajectory_stage MUST be exactly one of: rising, stalling, plateau, insufficient
5. Every list must be non-empty unless the input genuinely supports nothing (then return [] and explain inside trajectory)
6. Keep each string field dense and specific; no filler praise, no restating the input schema

You must return JSON (all fields present):
{
  "headline": "one-line verdict of this candidate's current growth state",
  "trajectory": "growth-trajectory narrative grounded in session ids and scores, 200-400 chars",
  "trajectory_stage": "rising | stalling | plateau | insufficient",
  "recurring_weaknesses": [
    {"skill": "weakness pattern name", "count": <sessions it appeared in>, "trend": "worsening | stable | improving", "advice": "one concrete counter-move"}
  ],
  "improving_areas": ["area that measurably improved, with session evidence"],
  "resume_gap_insights": ["gap between interview performance and resume claims, each citing the evidence"],
  "training_plan": [
    {"area": "focus area", "based_on": "the evidence that motivates it", "actions": ["2-4 concrete practice actions"]}
  ]
}"""
)


def growth_insight_user_message(
    *,
    sessions_json: str,
    resume_summary: str,
    profile_summary: str,
    locale: str = "zh-CN",
) -> str:
    """Assemble the growth-analysis user message (context built by the service layer)."""
    parts = [f"## Interview report summaries (newest first)\n{sessions_json}"]
    if resume_summary.strip():
        parts.append(f"## Latest resume deep review\n{resume_summary}")
    else:
        parts.append("## Latest resume deep review\n(no scored resume available yet)")
    if profile_summary.strip():
        parts.append(f"## Candidate profile\n{profile_summary}")
    parts.append(growth_language_instruction(locale))
    return "\n\n".join(parts)


__all__ = [
    "GROWTH_INSIGHT_SYSTEM",
    "growth_insight_user_message",
]
