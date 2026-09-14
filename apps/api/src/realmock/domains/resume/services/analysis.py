"""Resume deep-review orchestration: heal text → Agent loop → persist.

The evaluation JSON contract is ``ResumeAnalysis``. How evidence is gathered
is owned by the resume-review Agent (tools + plan), not a fixed LLM pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from realmock.domains.resume.agents.review import OnReviewEvent, run_resume_review
from realmock.domains.resume.schemas.analysis import ResumeAnalysis
from realmock.domains.resume.schemas.limits import (
    COMMIT_RETRY_ATTEMPTS,
    COMMIT_RETRY_DELAY_SECONDS,
    DIMENSION_HINTS,
    DIMENSION_KEYS,
    MIN_REVIEW_TEXT_CHARS,
    MIN_SCORED_DIMENSIONS,
    RAW_TEXT_STORE_CHARS,
)
from realmock.domains.resume.schemas.locale import infer_resume_text_locale
from realmock.domains.resume.services.analysis_normalize import (
    benchmark_percentile_from_score,
    compute_score_from_dims,
    normalize_resume_analysis_payload,
)
from realmock.domains.resume.services.extract import extract_resume_text
from realmock.domains.resume.services.files import find_resume_file
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.core.errors import ApiBusinessError, raise_error
from realmock.platform.models import Resume

logger = logging.getLogger(__name__)

# NOTE: OnReviewEvent is defined once in agents.review and re-exported here
# via the import above, so the SSE callback contract has a single source.


async def _commit_with_retry(db: Session) -> None:
    """Commit and briefly retry on SQLite ``database is locked``.

    Runs on the event loop — wait with ``asyncio.sleep`` so SSE/event-loop tasks are not blocked.
    """
    for attempt in range(1, COMMIT_RETRY_ATTEMPTS + 1):
        try:
            db.commit()
            return
        except OperationalError as e:
            db.rollback()
            if attempt == COMMIT_RETRY_ATTEMPTS or "locked" not in str(e).lower():
                raise
            logger.warning(
                "Resume analysis commit hit SQLite lock, retry %s: %s", attempt, e
            )
            await asyncio.sleep(COMMIT_RETRY_DELAY_SECONDS * attempt)


def _analysis_has_substance(analysis: ResumeAnalysis) -> bool:
    """Reject empty/truncated payloads that would otherwise persist as score 0."""
    texts = (
        analysis.content_review,
        analysis.layout_review,
        analysis.typography_review,
        analysis.overall_narrative,
        analysis.headline,
        analysis.first_impression,
    )
    text_len = sum(len((part or "").strip()) for part in texts)
    scored = len(analysis.dimension_scores)
    return text_len >= MIN_REVIEW_TEXT_CHARS or scored >= MIN_SCORED_DIMENSIONS


def _scoring_needs_recovery(analysis: ResumeAnalysis) -> bool:
    """True when score is 0 and dimension coverage below MIN_SCORED_DIMENSIONS."""
    if analysis.score > 0:
        return False
    return len(analysis.dimension_scores) < MIN_SCORED_DIMENSIONS


def _to_resume_analysis(payload: dict[str, Any], *, locale: str) -> ResumeAnalysis:
    data = normalize_resume_analysis_payload(
        payload if isinstance(payload, dict) else {},
        locale=locale,
    )
    analysis = ResumeAnalysis.model_validate(data)
    if not _analysis_has_substance(analysis):
        logger.warning(
            "Resume analysis lacks substance text_len=%s dims=%s keys=%s",
            sum(
                len((part or "").strip())
                for part in (
                    analysis.content_review,
                    analysis.layout_review,
                    analysis.typography_review,
                    analysis.overall_narrative,
                    analysis.headline,
                    analysis.first_impression,
                )
            ),
            len(analysis.dimension_scores),
            sorted(str(k) for k in (payload or {}).keys())[:24],
        )
        raise_error("C0002")
    computed = compute_score_from_dims(
        analysis.dimension_scores, dict(analysis.dimension_weights or {})
    )
    if computed is not None:
        analysis.score = computed
    analysis.benchmark_percentile = benchmark_percentile_from_score(analysis.score)
    return analysis


def resolve_review_locale(r: Resume) -> str:
    """Plan titles and evaluation language follow the resume body, not the UI locale."""
    return infer_resume_text_locale(r.raw_text, r.parsed_profile, r.filename)


def _repair_prompt_schema() -> str:
    lines = [
        f'    "{key}": {{"score": 0-100, "comment": "{DIMENSION_HINTS[key]}"}}'
        for key in DIMENSION_KEYS
    ]
    return "{\n" + ",\n".join(lines) + "\n  }"


async def _request_score_repair(
    llm: LLMClient,
    analysis: ResumeAnalysis,
    *,
    locale: str,
) -> dict[str, Any] | None:
    chat_json = getattr(llm, "chat_json", None)
    if chat_json is None:
        return None
    source = {
        "headline": analysis.headline,
        "first_impression": analysis.first_impression,
        "overall_narrative": analysis.overall_narrative,
        "content_review": analysis.content_review,
        "layout_review": analysis.layout_review,
        "typography_review": analysis.typography_review,
        "strengths": analysis.strengths,
        "weaknesses": analysis.weaknesses,
        "dimension_scores_schema": _repair_prompt_schema(),
    }
    try:
        recovered = await chat_json(
            [
                {
                    "role": "system",
                    "content": (
                        "The resume review narrative is present but overall score / "
                        "dimension_scores are missing or stuck at 0. Return JSON with "
                        "keys score and dimension_scores only. Every catalog key is "
                        f"required. Write comments in {locale}. Scores must match the "
                        "narrative; do not invent new critique text."
                    ),
                },
                {"role": "user", "content": json.dumps(source, ensure_ascii=False)[:12_000]},
            ],
            temperature=0.1,
            max_tokens=4_000,
        )
    except Exception as exc:
        logger.warning("Resume score recovery failed: %s", exc)
        return None
    return recovered if isinstance(recovered, dict) else None


async def _recover_incomplete_scores(
    llm: LLMClient,
    analysis: ResumeAnalysis,
    *,
    locale: str,
) -> ResumeAnalysis:
    recovered = await _request_score_repair(llm, analysis, locale=locale)
    if not isinstance(recovered, dict):
        raise_error("C0002")
    merged = analysis.model_dump()
    dims = recovered.get("dimension_scores")
    if dims:
        merged["dimension_scores"] = dims
    if recovered.get("score") is not None:
        merged["score"] = recovered["score"]
    try:
        repaired = _to_resume_analysis(merged, locale=locale)
    except ApiBusinessError:
        raise
    except Exception as exc:
        raise_error("C0002", cause=exc)
    if len(repaired.dimension_scores) < MIN_SCORED_DIMENSIONS:
        raise_error("C0002")
    return repaired


async def analyze_resume_with_llm(
    r: Resume,
    db: Session,
    *,
    locale: str | None = None,
    on_event: OnReviewEvent | None = None,
) -> ResumeAnalysis:
    """Run deep review for one resume and persist ``ResumeAnalysis``.

    Failures raise the same business codes as the route (A0006 / A1004 / C0001 /
    C0002 / B1001). ``locale`` is the UI chrome language from HTTP and is not
    used: plan titles and evaluation copy follow the resume body.
    ``on_event`` receives live plan / tool / thinking dicts for SSE.
    """
    if locale:
        logger.debug("Ignoring UI locale %s; review language follows the resume", locale)
    llm = LLMClient.from_db(db, reasoning_effort="max")
    if not llm.api_key:
        raise_error("A0006")

    if not (r.raw_text or "").strip():
        file_path = find_resume_file(r)
        if file_path is None:
            raise_error("A1004")
        r.raw_text = (await extract_resume_text(file_path, r.file_type, llm, db))[:RAW_TEXT_STORE_CHARS]
        await _commit_with_retry(db)

    review_locale = resolve_review_locale(r)

    try:
        payload = await run_resume_review(
            r, db, llm, locale=review_locale, on_event=on_event
        )
    except ApiBusinessError:
        raise
    except Exception as e:
        logger.exception("Resume review agent failed")
        raise_error("C0001", cause=e)

    payload.pop("_agent_steps", None)
    try:
        analysis = _to_resume_analysis(payload, locale=review_locale)
    except ApiBusinessError:
        raise
    except Exception as e:
        logger.warning("Resume analysis structure validation failed: %s", e, exc_info=True)
        raise_error("C0002", cause=e)

    if _scoring_needs_recovery(analysis):
        analysis = await _recover_incomplete_scores(llm, analysis, locale=review_locale)

    try:
        r.score = analysis.score
        r.analysis = analysis.model_dump_json()
        await _commit_with_retry(db)
    except Exception as e:
        logger.exception("Resume analysis DB write failed")
        db.rollback()
        raise_error("B1001", cause=e)

    return analysis
