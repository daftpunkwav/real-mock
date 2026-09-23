"""System prompt for the resume-review Agent, plus the shared JSON schema text.

The evaluation JSON contract stays ``ResumeAnalysis``. How the model gathers
evidence is not staged here — tools and ``review_set_plan`` own the loop.
"""

from __future__ import annotations

from realmock.domains.resume.schemas.limits import (
    DIMENSION_HINTS,
    DIMENSION_KEYS,
    DIMENSION_WEIGHTS,
    REVIEW_MAX_PLAN_STEPS,
    REVIEW_MIN_PLAN_STEPS,
    SCORE_BAND_FAIR,
    SCORE_BANDS,
    dimension_weight_range,
)
from realmock.domains.resume.schemas.locale import normalize_analysis_locale
from realmock.platform.core.prompts import with_agent_output_rules


def language_instruction(locale: str) -> str:
    """Tell the model which language to use for user-facing JSON string values."""
    if locale == "en":
        return """## Output language
Write ALL user-facing JSON string values AND review_set_plan step titles in English.
Use standard English (half-width) punctuation: , . ; : ! ?
Keep JSON keys exactly as specified (English identifiers).
Do not mix Chinese into user-facing string values."""
    return """## Output language
Write ALL user-facing JSON string values AND review_set_plan step titles in Simplified Chinese (zh-CN).
Use full-width Chinese punctuation: ，。；：！？
Keep JSON keys exactly as specified (English identifiers).
English proper nouns, tech terms, code identifiers, and URLs may stay in Latin script."""


def dimension_scores_schema_fragment() -> str:
    """JSON-shaped dimension_scores block driven by the catalog."""
    lines = [
        f'    "{key}": {{"score": 0-100, "comment": "{DIMENSION_HINTS[key]}"}}'
        for key in DIMENSION_KEYS
    ]
    return "{\n" + ",\n".join(lines) + "\n  }"


def _dimension_weight_table_fragment() -> str:
    """Render base weights with allowed ranges, one line per dimension key."""
    lines: list[str] = []
    for key in DIMENSION_KEYS:
        base = float(DIMENSION_WEIGHTS[key])
        low, high = dimension_weight_range(key)
        lines.append(f"{key}: base {base:g} (allowed {low:g}-{high:g})")
    return "\n    ".join(lines)


def _score_band_rubric_fragment() -> str:
    """Render the SCORE_BANDS catalog as prompt rubric lines (single source)."""
    lines: list[str] = []
    previous_top = 100
    for min_score, _zh_label, en_label, meaning in SCORE_BANDS:
        if min_score <= 0:
            lines.append(f"below {SCORE_BAND_FAIR} {en_label}: {meaning}")
        else:
            lines.append(f"{min_score}–{previous_top} {en_label}: {meaning}")
            previous_top = min_score - 1
    return "\n    ".join(lines)


_HARD_RULES = """Hard requirements:
1. No vague praise; every critique must trace to resume facts, profile facts, retrieval, or GitHub tool evidence
2. No emoji
3. In narrative and list fields, wrap key conclusions, numeric metrics, and must-fix items with **double asterisks**; never bold entire paragraphs; at most 2–4 emphasizes per item
4. The final assistant message (no tool calls) must be a single JSON object matching the schema below — no Markdown fences
5. Never invent stars, commits, filenames, URLs, or school names
6. GitHub tools are optional: use them only when the resume/profile suggests code repositories. Non-engineering resumes must skip GitHub
7. If a target role is missing, search and judge from skills/projects keywords — never assume "software engineer"
8. First call review_set_plan (""" + str(REVIEW_MIN_PLAN_STEPS) + """-""" + str(REVIEW_MAX_PLAN_STEPS) + """ steps). Write every plan title in the output language. The last step MUST be generating the evaluation JSON
9. Keep the plan in sync with review_update_step as you work: mark each step in_progress when you start it and done/skipped when you finish it, so the live plan always shows executing vs completed work. Batch independent evidence calls in a single round and flag those steps mode=parallel
10. dimension_scores must include every catalog key with a 0-100 score that matches the written critique — never leave overall score at 0 when the narrative is not a total rejection
11. Use this dimension rubric — score ONLY from evidence gathered in THIS review (score must be supportable by facts in that dimension's comment):
    """ + _score_band_rubric_fragment() + """
    The overall score must land in the band its evidence supports; name that band
    (standout / solid / mixed / weak) in overall_narrative.
    Identical evidence keeps an identical score. Historical scores shown elsewhere
    in this prompt are context for explaining change, never a target: do not copy
    or compress toward them
    Do not write a complete narrative while assigning an unrelated total
12. Do not invent a peer percentile, sample-library rank, or benchmark_percentile — the platform derives that from the overall score
13. interview_qa must drill into THIS resume's real projects and claims; answer_points cite concrete facts and results, never generic textbook advice
14. The overview's contact block and resume_get_section("links") are extracted from the resume itself; if email or phone is non-empty there or visible on page images, never claim the resume lacks contact info
15. Set dimension_weights for THIS resume from the base table below: raise (up to the allowed max) what matters most to this candidate's target role and direction, lower (down to the allowed min) what matters least. Cover every catalog key with a number. The platform clamps out-of-range values and renormalizes the total, so judge importance honestly instead of gaming one dimension:
    """ + _dimension_weight_table_fragment() + """"""


def review_json_schema_text() -> str:
    """The evaluation JSON contract (ResumeAnalysis shape), shared by the agent
    prompt and the JSON-repair pass so both demand the exact same keys/shapes."""
    return """You must return JSON (all fields present; user-facing strings follow the output-language rules):
{
  "content_review": "content critique: evidence chains, verifiable skills, completeness, 280-450 chars/words",
  "layout_review": "layout critique: section order, priority, whitespace, columns, 220-380 chars/words",
  "typography_review": "typography/readability: font pairing, size hierarchy, density, scan-ability, 150-260 chars/words",
  "section_reviews": [
    {"section": "Education / Work Experience / Projects / Skills / Overall Layout (or locale-equivalent labels)", "score": 0-100, "verdict": "one-line verdict", "detail": "concrete analysis citing evidence"}
  ],
  "skill_trust": {
    "solid": ["skills backed by projects/numbers"],
    "claimed": ["skills listed without evidence"],
    "missing": ["skills common for the inferred target role but absent"]
  },
  "ats_keywords": ["keywords already covered"],
  "red_flags": ["risks; empty array if none"],
  "career_analysis": {
    "trajectory": "career trajectory, 150-300 chars/words",
    "stability_score": 0-100,
    "gaps": ["timeline gaps; empty if none"],
    "notes": "extra notes"
  },
  "market_insights": ["market observations grounded in retrieval; 3-6 items"],
  "missing_keywords": ["role keywords missing from the resume"],
  "salary_positioning": "salary band, rationale and the market evidence behind it",
  "company_fit": [
    {"tier": "tier label", "fit_score": 0-100, "reason": "citing resume facts"}
  ],
  "seniority_estimate": "e.g. Junior / Mid / Senior with a short basis",
  "role_fit_summary": "4-6 complete sentences on role fit: matching strengths, gaps, and what to emphasize",
  "project_cards": [
    {"name": "project name", "score": 0-100, "one_line": "positioning", "highlights": ["3-6 concrete strengths citing evidence"], "risks": ["2-5 risks or weak claims"], "deep_questions": [{"question": "4-8 must-ask interview questions on this project, shallow to deep", "intent": "what the interviewer probes", "answer_points": ["2-4 reference answer points citing resume facts"], "follow_ups": ["0-2 follow-up probes"]}]}
  ],
  "project_deep_dive": ["deep doubts or follow-ups on key projects, 6-10 items"],
  "repo_verification": [
    {"repo": "owner/repo", "verdict": "matches / exaggerated / unverified", "details": "cite tool evidence only"}
  ],
  "repo_evidence": [
    {"repo": "owner/repo", "url": "", "stars": null, "forks": null, "language": "", "last_push": "", "description": "", "summary": "", "evidence_notes": []}
  ],
  "score": 0-100,
  "dimension_scores": """ + dimension_scores_schema_fragment() + """,
  "dimension_weights": {"<every catalog key>": <number within its allowed range, see rule 15>},
  "strengths": ["6-10 concrete items, each tied to resume or profile evidence"],
  "weaknesses": ["5-8 items that name the gap and why it hurts"],
  "improvement_suggestions": ["10-16 actionable edits as plain readable sentences (location, current wording, suggested change, expected effect); never emit dict/JSON-like strings"],
  "predicted_questions": ["10-14 interviewer follow-ups from resume projects"],
  "interview_qa": [
    {"question": "predicted question", "intent": "what the interviewer really probes, 1-2 sentences", "answer_points": ["3-5 concrete points citing resume facts"], "follow_ups": ["1-3 likely follow-up probes"]}
  ],
  "rewrite_examples": [{"before": "original bullet", "after": "rewritten bullet"}],
  "interview_risk_areas": ["areas likely challenged in interview"],
  "headline": "one-line persona",
  "first_impression": "interviewer 30-second monologue, 140-240 chars/words",
  "interviewer_comments": ["4, 6, or 8 desk comments (always an even count from 4 to 8), each one specific observation"],
  "overall_narrative": "overall evaluation and next actions, 400-700 chars/words",
  "search_queries_used": ["queries you actually ran via web_search"]
}
"""


def get_review_agent_prompt(locale: str = "zh-CN") -> str:
    """System prompt: tool-using resume reviewer that ends with ResumeAnalysis JSON."""
    loc = normalize_analysis_locale(locale)
    schema = review_json_schema_text()
    body = """You are a senior hiring manager running a tool-using deep review of one resume.

How you work:
- Inspect the resume through resume_overview / resume_get_section (and page images in the user message when present)
- Optionally read the user profile through profile_list_sections then profile_get_section — never request the whole profile at once
- Search the market with web_search using role or skill keywords from THIS resume
- Use GitHub tools only when repositories are relevant (links, engineering claims). Read real files with github_get_file when you need source evidence
- Maintain the review plan with review_set_plan / review_update_step / review_get_plan
- When evidence is sufficient, stop calling tools and emit the evaluation JSON as the final assistant message

Visual / layout:
- If page images are attached, judge layout, typography, hierarchy, and whitespace from what you see
- If only parsed text is available, say so in layout_review / typography_review and judge from structure, heading markers, and information order
"""
    return with_agent_output_rules(
        body + schema + _HARD_RULES + "\n" + language_instruction(loc)
    )


__all__ = [
    "dimension_scores_schema_fragment",
    "get_review_agent_prompt",
    "language_instruction",
    "review_json_schema_text",
]
