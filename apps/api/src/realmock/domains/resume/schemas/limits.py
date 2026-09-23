"""Single source for resume-domain limits, allowlists, and dimension keys.

Responsibilities:
- Declare upload, parse, render, analysis, evidence, and market-cache limits
- Declare allowed extensions, MIME map, analysis locales, and dimension keys
- Re-export platform protocol upload limits so routes do not scatter literals

ORM column lengths stay on ``Resume``; contract_guard rejects drift vs this catalog.
Must not import FastAPI, ORM, or Pydantic models.
"""

from __future__ import annotations

from typing import Literal

from realmock.platform.core.constants import (
    RESUME_ALLOWED_EXTENSIONS,
    RESUME_MAX_UPLOAD_BYTES,
)

# ── Upload / HTTP (aliases of platform protocol constants) ──────────────

ALLOWED_EXTENSIONS: frozenset[str] = RESUME_ALLOWED_EXTENSIONS
MAX_UPLOAD_BYTES: int = RESUME_MAX_UPLOAD_BYTES
MAX_PARALLEL_ANALYZE: int = 3
FILENAME_MAX_LENGTH: int = 255
FILE_TYPE_MAX_LENGTH: int = 20

FILE_MIME: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "md": "text/markdown",
    "txt": "text/plain",
}

# ── Analysis locales ────────────────────────────────────────────────────

ANALYSIS_LOCALES: tuple[str, ...] = ("zh-CN", "en")
DEFAULT_ANALYSIS_LOCALE: Literal["zh-CN", "en"] = "zh-CN"

# ── Persistence / LLM context ───────────────────────────────────────────

RAW_TEXT_STORE_CHARS: int = 50_000
PARSE_LLM_CHARS: int = 15_000
PARSE_FALLBACK_SUMMARY_CHARS: int = 500

# ── Format extraction (DoS / zip-bomb guards) ───────────────────────────

MAX_PDF_PAGES: int = 50
MAX_DOCX_ZIP_ENTRIES: int = 200
MAX_DOCX_UNCOMPRESSED_BYTES: int = 30 * 1024 * 1024
MAX_EXTRACTED_CHARS: int = 100_000
MAX_PARAGRAPHS: int = 5_000

# ── PDF render / vision transcription ───────────────────────────────────

MAX_VISION_PAGES: int = 8
PDF_RENDER_ZOOM: float = 2.0
PAGE_PREVIEW_ZOOM: float = 2.5
MAX_RENDER_PX: int = 4096
RENDER_CONCURRENCY: int = 2
# Per-page vision transcription calls run concurrently; this bounds the LLM
# request fan-out for one resume (independent of the fitz render semaphore).
TRANSCRIBE_CONCURRENCY: int = 3

# ── Deep-review Agent ───────────────────────────────────────────────────

COMMIT_RETRY_ATTEMPTS: int = 3
COMMIT_RETRY_DELAY_SECONDS: float = 1.5
# NOTE: reserved, currently unused — repo evidence is capped per-field by
# MAX_README_CHARS / MAX_EVIDENCE_FILE_CHARS instead. Do not tune this
# expecting an effect until a consumer is wired (and added to
# client_limits_payload + contract_guard coverage).
REPO_EVIDENCE_JSON_BUDGET: int = 4000

# Rounds before the cap that receive the soft-landing countdown nudges; the
# outer half is advisory ("conclude evidence gathering"), the inner half is
# urgent ("no new explorations"). The last round always gets the wrap-up hint
# and (with final_round_tool_free) no tools at all.
REVIEW_COUNTDOWN_ROUNDS: int = 10
REVIEW_MAX_ROUNDS: int = 30
REVIEW_MAX_TOOLS_PER_ROUND: int = 6
# Soft ceiling on tool calls across the whole review: beyond it calls are
# refused with a "write the final answer" observation instead of executing,
# but the loop keeps running so the model can always produce its answer.
REVIEW_MAX_TOTAL_TOOL_CALLS: int = 80
# Deterministic head+tail cap for one tool observation (attention bound, not a
# context-space bound — big-context models keep raw evidence).
REVIEW_OBSERVATION_MAX_CHARS: int = 16_000
REVIEW_MAX_PLAN_STEPS: int = 15
REVIEW_MIN_PLAN_STEPS: int = 8
# Post-loop finalize passes. Each wait_for must sit ABOVE the transport
# ceiling (LLM_CHAT_TIMEOUT_SECONDS = 480s): these bounds only catch
# pathological hangs, never a slow model legitimately thinking through a long
# chain of thought. ReadTimeout is not retried at transport level, so the
# worst real call is one transport attempt.
REVIEW_REPAIR_TIMEOUT_SECONDS: float = 540.0
# The tool-free synthesis call after a loop break re-sends the whole history;
# the bound below is a hang safety net, not a thinking deadline.
REVIEW_FORCED_FINAL_TIMEOUT_SECONDS: float = 540.0
# Self-correction finalize phase (model re-emits its own malformed JSON over
# the full loop history): same hang exposure as the forced-final call, so it
# gets the same class of bound. On timeout the chain falls through to repair.
REVIEW_SELF_CORRECTION_TIMEOUT_SECONDS: float = 540.0
# Score-recovery pass (chat_json over the review narrative).
REVIEW_SCORE_RECOVERY_TIMEOUT_SECONDS: float = 300.0
# Responses-protocol reasoning models count reasoning tokens toward this cap;
# a full Chinese evaluation JSON plus high-effort reasoning exceeds 16k.
REVIEW_MAX_OUTPUT_TOKENS = 32_768
REVIEW_SEARCH_MAX_RESULTS: int = 8
REVIEW_KEEP_RECENT_MESSAGES: int = 32
SSE_HEARTBEAT_SECONDS: float = 15.0
# Persist-time floor so a truncated/empty JSON is not stored as a successful review.
REVIEW_MIN_SCORED_DIMENSIONS: int = 4
REVIEW_MIN_TEXT_CHARS: int = 40
REVIEW_AGENT_TEMPERATURE: float = 0.15
SCORE_BAND_FAIR: int = 55
SCORE_BAND_STRONG: int = 70
SCORE_BAND_STANDOUT: int = 85
PERCENTILE_FLOOR: int = 8
PERCENTILE_CEILING: int = 92
MAX_RESUME_VERSIONS: int = 6

# ── DOCX structure extraction ───────────────────────────────────────────

MAX_DOCX_TABLES: int = 40
MAX_DOCX_TABLE_ROWS: int = 40

# ── GitHub evidence ─────────────────────────────────────────────────────

MAX_EVIDENCE_REPOS: int = 3
MAX_README_CHARS: int = 1200
MAX_EVIDENCE_FILE_CHARS: int = 1200
MAX_EVIDENCE_COMMITS: int = 3
KEY_FILE_PATTERNS: tuple[str, ...] = (
    "cargo.toml",
    "package.json",
    "pyproject.toml",
    "go.mod",
    "pom.xml",
    "main.rs",
    "main.py",
    "main.go",
    "index.ts",
)

# ── Market retrieval cache ──────────────────────────────────────────────

MAX_SEARCH_QUERIES: int = 5
MARKET_CACHE_MAX: int = 8
MARKET_SEARCH_HITS_PER_QUERY: int = 8

# ── Equal-weight review dimensions (prompt + frontend radar) ────────────

DIMENSION_KEYS: tuple[str, ...] = (
    "structure_clarity",
    "visual_layout",
    "typography",
    "impact_quantification",
    "tech_depth",
    "project_narrative",
    "role_fit",
    "keyword_ats",
    "credibility",
    "seniority_signal",
    "growth_signal",
    "collaboration_signal",
)

# Prompt-only hints; keys must equal DIMENSION_KEYS (enforced by contract_guard).
DIMENSION_HINTS: dict[str, str] = {
    "structure_clarity": "structure, information density, scan path — be specific",
    "visual_layout": "layout: column width, whitespace, alignment, single vs multi-column",
    "typography": "type hierarchy, size contrast, CJK/Latin mixing, line spacing",
    "impact_quantification": "outcome quantification and business impact",
    "tech_depth": "technical depth and stack fit",
    "project_narrative": "project narrative completeness (context-ownership-hard parts-results)",
    "role_fit": "fit to target role",
    "keyword_ats": "keywords and ATS friendliness",
    "credibility": "credibility and consistency (timeline/ownership/skills)",
    "seniority_signal": "seniority signal and ownership",
    "growth_signal": "growth potential: learning speed, escalating challenges, self-drive evidence",
    "collaboration_signal": "collaboration: team role, cross-function, open-source traces",
}

# Overall-score math: weight-normalized mean of dimension scores. The model may
# shift each weight within WEIGHT_ADJUST_RATIO of base (floored at WEIGHT_FLOOR)
# for the resume at hand; the platform clamps out-of-range values and
# renormalizes, so no dimension can be zeroed out or dominate the total.
# Keys must equal DIMENSION_KEYS (enforced by contract_guard).
DIMENSION_WEIGHTS: dict[str, float] = {
    "structure_clarity": 7.0,
    "visual_layout": 4.0,
    "typography": 4.0,
    "impact_quantification": 12.0,
    "tech_depth": 13.0,
    "project_narrative": 8.0,
    "role_fit": 12.0,
    "keyword_ats": 8.0,
    "credibility": 10.0,
    "seniority_signal": 8.0,
    "growth_signal": 6.0,
    "collaboration_signal": 8.0,
}
WEIGHT_ADJUST_MIN_RATIO = 0.5
WEIGHT_ADJUST_MAX_RATIO = 1.5
WEIGHT_FLOOR = 1.0


def dimension_weight_range(key: str) -> tuple[float, float]:
    """Allowed (min, max) model weight for one dimension key."""
    base = float(DIMENSION_WEIGHTS.get(key, 1.0))
    low = max(WEIGHT_FLOOR, round(base * WEIGHT_ADJUST_MIN_RATIO, 2))
    high = round(base * WEIGHT_ADJUST_MAX_RATIO, 2)
    return (low, high)

# Explicit overall-score bands: single source for the prompt rubric and UI
# labels. Entries are (min_score, zh_label, en_label, meaning), high to low.
SCORE_BANDS: tuple[tuple[int, str, str, str], ...] = (
    (SCORE_BAND_STANDOUT, "突出", "standout", "quantified outcomes plus verifiable claims, rare gaps"),
    (SCORE_BAND_STRONG, "扎实", "solid", "complete coverage, minor gaps"),
    (SCORE_BAND_FAIR, "参差", "mixed", "notable gaps or thin evidence"),
    (0, "偏弱", "weak", "weak or missing evidence"),
)


def score_band_label(score: int, *, locale: str = "zh-CN") -> str:
    """Band label for an overall score (clamped to [0, 100])."""
    clamped = max(0, min(100, int(score)))
    for min_score, zh_label, en_label, _meaning in SCORE_BANDS:
        if clamped >= min_score:
            return zh_label if locale == "zh-CN" else en_label
    return SCORE_BANDS[-1][1] if locale == "zh-CN" else SCORE_BANDS[-1][2]


def client_limits_payload() -> dict[str, object]:
    """Stable dict for ``GET /resume/limits`` and OpenAPI (sorted extensions)."""
    return {
        "allowed_extensions": sorted(ALLOWED_EXTENSIONS),
        "max_upload_bytes": MAX_UPLOAD_BYTES,
        "max_parallel_analyze": MAX_PARALLEL_ANALYZE,
        "dimension_keys": list(DIMENSION_KEYS),
        "analysis_locales": list(ANALYSIS_LOCALES),
        "filename_max_length": FILENAME_MAX_LENGTH,
        "file_type_max_length": FILE_TYPE_MAX_LENGTH,
        "max_resume_versions": MAX_RESUME_VERSIONS,
        "percentile_floor": PERCENTILE_FLOOR,
        "percentile_ceiling": PERCENTILE_CEILING,
        "min_scored_dimensions": REVIEW_MIN_SCORED_DIMENSIONS,
        "score_band_fair": SCORE_BAND_FAIR,
        "score_band_strong": SCORE_BAND_STRONG,
        "score_band_standout": SCORE_BAND_STANDOUT,
    }
