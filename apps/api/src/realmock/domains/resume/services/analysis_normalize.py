"""Tolerant normalize of resume-analysis LLM payloads and overall score math.

Responsibilities:
- Coerce messy LLM JSON into ``ResumeAnalysis``-shaped dicts
- Clamp scores, clip lists, normalize rewrite / section / repo nested blobs
- Weight-normalized mean of dimension scores for a deterministic overall score

Must not import FastAPI, ORM, or call an LLM.
"""

from __future__ import annotations

import ast
import json
import re
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from realmock.domains.resume.schemas.limits import (
    DIMENSION_WEIGHTS,
    PERCENTILE_CEILING,
    PERCENTILE_FLOOR,
    dimension_weight_range,
)
from realmock.platform.core.prompts import normalize_cn_punctuation_tree

if TYPE_CHECKING:
    from realmock.domains.resume.schemas.analysis import DimensionScore


def _loads_rewrite_dict(text: str) -> dict | None:
    """Parse a stringified rewrite dict via JSON then literal_eval; else None."""
    try:
        parsed = json.loads(text.replace("'", '"'))
    except Exception:
        try:
            parsed = ast.literal_eval(text)
        except Exception:
            return None
    return parsed if isinstance(parsed, dict) else None


def _keyed_rewrite_pair(text: str) -> tuple[str, str]:
    """Extract before/after via explicit ``'before': ... 'after':`` key regexes."""
    bm = re.search(
        r"['\"]before['\"]\s*:\s*['\"](.+?)['\"]\s*,\s*['\"]after['\"]",
        text,
        re.I | re.S,
    )
    am = re.search(r"['\"]after['\"]\s*:\s*['\"](.+?)['\"]\s*}", text, re.I | re.S)
    if bm and am:
        return bm.group(1).strip(), am.group(1).strip()
    return "", ""


def _labeled_rewrite_pair(text: str) -> tuple[str, str]:
    """Extract before/after via labeled markers (before/after, 改前, 【改前】)."""
    m = re.search(
        r"(?:\[\s*before\s*\]|before\s*[:：]|改前\s*[:：]|【\s*改前\s*】)\s*(.*?)\s*"
        r"(?:\[\s*after\s*\]|after\s*[:：]|After modification\s*[:：])\s*(.+)",
        text,
        re.I | re.S,
    )
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return "", ""


def _arrow_rewrite_pair(text: str) -> tuple[str, str]:
    """Split a ``before → after`` style string and strip key prefixes."""
    parts = re.split(r"\s*(?:→|->|=>)\s*", text, maxsplit=1)
    if len(parts) != 2:
        return "", ""
    before = re.sub(
        r"^(?:\[(?:\s*before(?:\s+change)?\s*)\]\s*|"
        r"before\s*change[:：]\s*|change\s*before[:：]\s*|before[:：]\s*)",
        "",
        parts[0],
        flags=re.I,
    ).strip()
    after = re.sub(
        r"^(?:\[(?:\s*after(?:\s+change)?\s*)\]\s*|"
        r"After modification[:：]\s*|after[:：]\s*)",
        "",
        parts[1],
        flags=re.I,
    ).strip()
    return before, after


def _strip_heading_markers(text: str) -> str:
    return re.sub(r"^\s*#{1,6}\s*", "", text)


def _normalize_rewrite_examples(raw: object) -> list[dict[str, str]]:
    """Normalize rewrite examples to ``[{before, after}]``, accepting str / dict."""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw[:20]:
        before = ""
        after = ""
        if isinstance(item, dict):
            before = str(item.get("before") or item.get("Before the change") or "").strip()
            after = str(item.get("after") or item.get("After modification") or "").strip()
        elif isinstance(item, str):
            text = item.strip()
            if text.startswith("{") and ("before" in text or "Before the change" in text):
                parsed = _loads_rewrite_dict(text)
                if isinstance(parsed, dict):
                    before = str(parsed.get("before") or parsed.get("Before the change") or "").strip()
                    after = str(parsed.get("after") or parsed.get("After modification") or "").strip()
                else:
                    before, after = _keyed_rewrite_pair(text)
            if not before and not after:
                before, after = _labeled_rewrite_pair(text)
            if not before and not after:
                before, after = _arrow_rewrite_pair(text)
        if before and after:
            # Rewrite bullets sometimes carry Markdown heading markers (### project name...); strip before display as plain text.
            before = _strip_heading_markers(before)
            after = _strip_heading_markers(after)
            out.append({"before": before[:1200], "after": after[:1200]})
    return out


def _clip_list_str(values: object, limit: int, item_max: int = 200) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(v).strip()[:item_max] for v in values if v is not None and str(v).strip()][:limit]


def _coerce_int_score(v: object) -> int | None:
    """Lenient int coercion: int / float / numeric strings (incl. ``"88.7"``); else None."""
    try:
        return int(v)  # type: ignore[arg-type, call-overload]
    except (TypeError, ValueError):
        pass
    try:
        return int(float(v))  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return None


def _clamp_score(v: int) -> int:
    """Clamp a coerced score into [0, 100]. Single source for score clamping."""
    return max(0, min(100, v))


def _norm_score(v: object) -> int:
    coerced = _coerce_int_score(v)
    return _clamp_score(coerced) if coerced is not None else 0


def _pick_overall_score(data: dict) -> int:
    """Use a numeric ``score`` as-is (including 0). Alias keys fill only a missing score.

    An explicit 0 is a real value for recovery / C0002 — do not overwrite it with
    leftover ``overall_score`` / ``total_score`` fields.
    """
    explicit = _coerce_int_score(data.get("score")) if "score" in data else None
    if explicit is not None:
        return _clamp_score(explicit)
    for key in ("overall_score", "total_score", "overallScore"):
        coerced = _coerce_int_score(data.get(key))
        if coerced is not None:
            return _clamp_score(coerced)
    return 0


def _coerce_dimension_map(raw: object) -> dict:
    """Accept a dict or a list of ``{key/dimension/name/id, score}`` objects."""
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, list):
        return {}
    out: dict = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = item.get("key") or item.get("dimension") or item.get("name") or item.get("id")
        if not key:
            continue
        out[str(key)[:64]] = item
    return out


def _normalize_section_reviews(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw[:8]:
        if not isinstance(item, dict):
            continue
        out.append({
            "section": str(item.get("section") or "").strip()[:40],
            "score": _norm_score(item.get("score")),
            "verdict": str(item.get("verdict") or "").strip()[:80],
            "detail": str(item.get("detail") or "").strip()[:1200],
        })
    return out


def _normalize_deep_questions(raw: object) -> list[dict]:
    """Project must-ask questions as drill cards; legacy rows store plain strings."""
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw[:8]:
        if isinstance(item, str):
            question = item.strip()
            if question:
                out.append(
                    {
                        "question": question[:400],
                        "intent": "",
                        "answer_points": [],
                        "follow_ups": [],
                    }
                )
            continue
        if isinstance(item, dict):
            question = str(item.get("question") or "").strip()
            if not question:
                continue
            out.append(
                {
                    "question": question[:400],
                    "intent": str(item.get("intent") or "")[:400],
                    "answer_points": _clip_list_str(item.get("answer_points"), 6, 400),
                    "follow_ups": _clip_list_str(item.get("follow_ups"), 4, 300),
                }
            )
    return out


def _normalize_project_cards(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw[:6]:
        if not isinstance(item, dict):
            continue
        out.append({
            "name": str(item.get("name") or "").strip()[:80],
            "score": _norm_score(item.get("score")),
            "one_line": str(item.get("one_line") or "").strip()[:120],
            "highlights": _clip_list_str(item.get("highlights"), 6, 300),
            "risks": _clip_list_str(item.get("risks"), 5, 300),
            "deep_questions": _normalize_deep_questions(item.get("deep_questions")),
        })
    return out


def _normalize_skill_trust(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    trust = {
        "solid": _clip_list_str(raw.get("solid"), 12, 80),
        "claimed": _clip_list_str(raw.get("claimed"), 12, 80),
        "missing": _clip_list_str(raw.get("missing"), 12, 80),
    }
    if not any(trust.values()):
        return None
    return trust


def _normalize_career_analysis(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    analysis = {
        "trajectory": str(raw.get("trajectory") or "").strip()[:1200],
        "stability_score": _norm_score(raw.get("stability_score")),
        "gaps": _clip_list_str(raw.get("gaps"), 6, 160),
        "notes": str(raw.get("notes") or "").strip()[:300],
    }
    if not analysis["trajectory"] and not analysis["gaps"]:
        return None
    return analysis


def _normalize_company_fit(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw[:6]:
        if not isinstance(item, dict):
            continue
        out.append({
            "tier": str(item.get("tier") or "").strip()[:40],
            "fit_score": _norm_score(item.get("fit_score")),
            "reason": str(item.get("reason") or "").strip()[:300],
        })
    return out


def _safe_public_url(raw: object, *, limit: int = 500) -> str:
    """Keep only absolute http(s) URLs from model-emitted fields.

    The analysis JSON comes from the model and can carry prompt-injected
    content; a ``javascript:`` / ``data:`` URL persisted here would later be
    bound to an ``href`` in the web UI. Non-http(s) values are dropped
    (empty string) instead of clipped.
    """
    value = str(raw or "").strip()[:limit]
    if not value:
        return ""
    try:
        parsed = urlparse(value)
    except ValueError:
        return ""
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return ""
    return value


def _normalize_repo_evidence(raw: object) -> list[dict]:
    """Keep schema fields from collector dicts; drop extra GitHub blobs."""
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw[:6]:
        if not isinstance(item, dict):
            continue
        stars = _coerce_int_score(item.get("stars"))
        forks = _coerce_int_score(item.get("forks"))
        out.append(
            {
                "repo": str(item.get("repo") or "")[:120],
                "url": _safe_public_url(item.get("url")),
                "stars": stars,
                "forks": forks,
                "language": str(item.get("language") or "")[:80],
                "last_push": str(item.get("last_push") or "")[:32],
                "description": str(item.get("description") or "")[:400],
                "summary": str(item.get("summary") or "")[:2000],
                "evidence_notes": _clip_list_str(item.get("evidence_notes"), 8, 400),
            }
        )
    return out


def _normalize_repo_verification(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    return [
        {
            "repo": str(v.get("repo") or "")[:120],
            "verdict": str(v.get("verdict") or "")[:120],
            "details": str(v.get("details") or "")[:800],
        }
        for v in raw
        if isinstance(v, dict)
    ][:6]


def _normalize_interview_qa(raw: object) -> list[dict]:
    """Structured interview drill items; a question without text carries no value."""
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw[:16]:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question") or "").strip()
        if not question:
            continue
        out.append(
            {
                "question": question[:400],
                "intent": str(item.get("intent") or "")[:400],
                "answer_points": _clip_list_str(item.get("answer_points"), 8, 400),
                "follow_ups": _clip_list_str(item.get("follow_ups"), 6, 300),
            }
        )
    return out


_SUGGESTION_KEYS = ("location", "current", "suggested", "effect")


def _format_structured_suggestion(data: dict) -> str | None:
    """Render a dict-shaped suggestion as one readable sentence."""
    loc = str(data.get("location") or "").strip()
    current = str(data.get("current") or "").strip()
    suggested = str(data.get("suggested") or "").strip()
    effect = str(data.get("effect") or "").strip()
    if not (loc or current or suggested or effect):
        return None
    head = f"【{loc}】" if loc else ""
    if current and suggested:
        body = f"{current} → {suggested}"
    else:
        body = current or suggested
    tail = f"（{effect}）" if effect else ""
    return f"{head}{body}{tail}".strip() or None


def _normalize_improvement_suggestions(raw: object) -> list[str]:
    """Clip suggestion bullets; dict-shaped items become readable sentences.

    The schema asks for location/current/suggested/effect content, so some
    models emit stringified dicts. Never surface raw ``{'location': ...}``
    text to the reader.
    """
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw[:20]:
        if isinstance(item, dict):
            formatted = _format_structured_suggestion(item)
            if formatted:
                out.append(formatted[:600])
            continue
        text = str(item).strip() if item is not None else ""
        if not text:
            continue
        parsed = _loads_rewrite_dict(text)
        if isinstance(parsed, dict) and any(k in parsed for k in _SUGGESTION_KEYS):
            formatted = _format_structured_suggestion(parsed)
            if formatted:
                out.append(formatted[:600])
            continue
        out.append(text[:600])
    return out


def _normalize_interviewer_comments(raw: object) -> list[str]:
    """Clip desk notes to 4-8 items with an even count for the paired-card UI.

    Drops blanks, caps at 8, and drops a trailing odd item when at least 4
    remain. Fewer than 4 are kept as-is: the model failed the contract, but
    inventing or destroying evidence is worse than an odd row.
    """
    items = [str(v).strip()[:400] for v in (raw if isinstance(raw, list) else [])]
    items = [v for v in items if v][:8]
    if len(items) % 2 == 1 and len(items) >= 4:
        items = items[:-1]
    return items


def _normalize_dimension_weights(raw: object) -> dict[str, float]:
    """Clamp model-set weights into the per-dimension allowed range.

    Unknown keys are dropped, missing keys fall back to the base table, and
    non-finite values are ignored — so a missing block degrades to the static
    table and the total stays deterministic.
    """
    out = dict(DIMENSION_WEIGHTS)
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        name = str(key)
        if name not in DIMENSION_WEIGHTS:
            continue
        try:
            weight = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if weight != weight or weight in (float("inf"), float("-inf")):
            continue
        low, high = dimension_weight_range(name)
        out[name] = min(high, max(low, weight))
    return out


def normalize_resume_analysis_payload(
    data: dict, *, locale: str = "zh-CN"
) -> dict:
    """Tolerant normalize of LLM payload so ``ResumeAnalysis`` validation can pass.

    When ``locale`` is ``zh-CN``, apply Chinese full-width punctuation
    normalization; for ``en`` (and other non-zh locales) skip that pass.
    """
    if not isinstance(data, dict):
        return {}
    out = dict(data)
    out["score"] = _pick_overall_score(out)
    for key in (
        "strengths", "weaknesses", "predicted_questions",
        "ats_keywords", "missing_keywords", "project_deep_dive", "red_flags",
        "interview_risk_areas", "market_insights", "search_queries_used",
    ):
        val = out.get(key)
        if not isinstance(val, list):
            out[key] = []
        else:
            out[key] = [str(x) for x in val if x is not None][:20]
    out["rewrite_examples"] = _normalize_rewrite_examples(out.get("rewrite_examples"))
    out["improvement_suggestions"] = _normalize_improvement_suggestions(
        out.get("improvement_suggestions")
    )
    out["interviewer_comments"] = _normalize_interviewer_comments(
        out.get("interviewer_comments")
    )
    dims = _coerce_dimension_map(out.get("dimension_scores"))
    normalized_dims: dict = {}
    for k, v in dims.items():
        key = str(k)[:64]
        if isinstance(v, dict):
            if "score" not in v:
                continue
            coerced = _coerce_int_score(v.get("score"))
            if coerced is None:
                continue
            sc = _clamp_score(coerced)
            normalized_dims[key] = {
                "score": sc,
                "comment": str(v.get("comment") or "")[:500],
            }
        elif isinstance(v, (int, float)):
            normalized_dims[key] = {"score": _norm_score(v), "comment": ""}
    out["dimension_scores"] = normalized_dims
    out["dimension_weights"] = _normalize_dimension_weights(out.get("dimension_weights"))
    for key in (
        "role_fit_summary",
        "seniority_estimate",
        "overall_narrative",
        "layout_review",
        "typography_review",
        "content_review",
        "headline",
        "first_impression",
    ):
        out[key] = str(out.get(key) or "")[:4000]
    pct = benchmark_percentile_from_score(out["score"])
    out["benchmark_percentile"] = pct
    out["section_reviews"] = _normalize_section_reviews(out.get("section_reviews"))
    out["project_cards"] = _normalize_project_cards(out.get("project_cards"))
    out["skill_trust"] = _normalize_skill_trust(out.get("skill_trust"))
    out["career_analysis"] = _normalize_career_analysis(out.get("career_analysis"))
    out["company_fit"] = _normalize_company_fit(out.get("company_fit"))
    out["salary_positioning"] = str(out.get("salary_positioning") or "")[:400]
    out["repo_evidence"] = _normalize_repo_evidence(out.get("repo_evidence"))
    out["repo_verification"] = _normalize_repo_verification(out.get("repo_verification"))
    out["interview_qa"] = _normalize_interview_qa(out.get("interview_qa"))
    # Full-width punctuation pass is only appropriate for zh-CN output.
    if locale == "zh-CN":
        normalized = normalize_cn_punctuation_tree(out)
        return normalized if isinstance(normalized, dict) else out
    return out


def compute_score_from_dims(
    dimension_scores: dict[str, DimensionScore],
    weights: dict[str, float] | None = None,
) -> int | None:
    """Deterministic overall score: weight-normalized mean of dimension scores, or None.

    Makes the total explainable and reproducible from dimension scores alone,
    avoiding free-form model totals that drift across runs. Unknown dimensions
    fall back to weight 1.0; with all-equal weights this is the plain mean.
    """
    table = weights if weights is not None else DIMENSION_WEIGHTS
    total = 0.0
    weight_sum = 0.0
    for key, value in (dimension_scores or {}).items():
        score = getattr(value, "score", None)
        if score is None:
            continue
        weight = float(table.get(str(key), 1.0))
        if weight <= 0:
            continue
        total += int(score) * weight
        weight_sum += weight
    if weight_sum <= 0:
        return None
    return round(total / weight_sum)


def benchmark_percentile_from_score(score: int) -> int:
    """Monotone map of overall score onto [PERCENTILE_FLOOR, PERCENTILE_CEILING].

    Not a real peer sample: the UI must label it as a conversion from the total.
    """
    clamped = _clamp_score(int(score))
    span = PERCENTILE_CEILING - PERCENTILE_FLOOR
    return PERCENTILE_FLOOR + round(span * clamped / 100)
