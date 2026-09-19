"""Prior-version score reference for re-review calibration.

Must not import FastAPI or call an LLM. Persistence lookups live in the store.

Same-file re-reviews intentionally receive NO historical scores: the model scores
strictly from the evidence gathered in the current review against the dimension
rubric in the agent prompt. Only a different, previously scored file version is
shown, purely as context for explaining what changed — never as a target.
"""

from __future__ import annotations

import json
from typing import Any

from realmock.domains.resume.schemas.limits import MIN_SCORED_DIMENSIONS


def _clip_list(values: object, limit: int, item_max: int = 160) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    for item in values:
        text = str(item).strip()
        if not text:
            continue
        out.append(text[:item_max])
        if len(out) >= limit:
            break
    return out


def compact_score_anchor(analysis: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a small score block, or None when dimension coverage is too thin."""
    if not isinstance(analysis, dict):
        return None
    raw_dims = analysis.get("dimension_scores")
    if not isinstance(raw_dims, dict):
        return None
    scores: dict[str, int] = {}
    for key, value in raw_dims.items():
        score: int | None = None
        if isinstance(value, dict) and "score" in value:
            raw_score: Any = value.get("score")
            try:
                score = int(raw_score)
            except (TypeError, ValueError):
                score = None
        elif isinstance(value, (int, float)):
            score = int(value)
        if score is None:
            continue
        scores[str(key)[:64]] = max(0, min(100, score))
    if len(scores) < MIN_SCORED_DIMENSIONS:
        return None
    overall = analysis.get("score")
    try:
        overall_n = max(0, min(100, int(overall))) if overall is not None else None
    except (TypeError, ValueError):
        overall_n = None
    return {
        "score": overall_n,
        "dimension_scores": scores,
        "strengths": _clip_list(analysis.get("strengths"), 3),
        "weaknesses": _clip_list(analysis.get("weaknesses"), 3),
    }


def format_prior_version_calibration(anchor: dict[str, Any], *, version_n: int) -> str:
    """Render a prior scored version as reference-only calibration text.

    Args:
        anchor: Compacted score anchor (totals, dimension scores, strengths/weaknesses).
        version_n: Prior version number cited in the header.

    Returns:
        Prompt text marking prior scores reference-only, never a target.
    """
    return (
        f"Prior scored version in this family: v{version_n} (a different file). "
        "Scores below are reference ONLY for explaining what changed between versions — "
        "never a target. Score THIS file strictly from its own evidence against the "
        "dimension rubric; do not copy or compress toward the prior totals. "
        "Unchanged evidence keeps its score; changed evidence must move its score, with reasons.\n"
        f"{json.dumps(anchor, ensure_ascii=False)}"
    )


def calibration_text(
    *,
    previous_analysis: dict[str, Any] | None = None,
    previous_version_n: int | None = None,
) -> str:
    """Prior-version reference block, or empty when no qualifying prior version.

    Same-file history is deliberately never rendered: re-reviews score from
    current evidence alone. Callers that need persistence (previous scored row)
    look it up themselves.
    """
    prior = compact_score_anchor(previous_analysis)
    if prior is None or previous_version_n is None:
        return ""
    return format_prior_version_calibration(prior, version_n=max(1, int(previous_version_n)))
