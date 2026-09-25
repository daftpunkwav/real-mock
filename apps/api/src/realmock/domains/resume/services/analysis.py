"""Resume deep-review orchestration: heal text → Agent loop → persist.

The evaluation JSON contract is ``ResumeAnalysis``. How evidence is gathered
is owned by the resume-review Agent (tools + plan), not a fixed LLM pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from realmock.domains.resume.agents.review import OnReviewEvent, run_resume_review
from realmock.domains.resume.schemas.analysis import ResumeAnalysis
from realmock.domains.resume.schemas.limits import (
    COMMIT_RETRY_ATTEMPTS,
    COMMIT_RETRY_DELAY_SECONDS,
    RAW_TEXT_STORE_CHARS,
    REVIEW_MIN_SCORED_DIMENSIONS,
    REVIEW_MIN_TEXT_CHARS,
    REVIEW_SCORE_RECOVERY_TIMEOUT_SECONDS,
)
from realmock.domains.resume.schemas.locale import infer_resume_text_locale
from realmock.domains.resume.services.analysis_normalize import (
    benchmark_percentile_from_score,
    compute_score_from_dims,
    normalize_resume_analysis_payload,
)
from realmock.domains.resume.prompts import (
    dimension_scores_schema_fragment,
    score_recovery_system,
)
from realmock.domains.resume.services.extract import extract_resume_text
from realmock.domains.resume.services.files import find_resume_file
from realmock.platform.capabilities.ai.llm.client import LLMClient
from realmock.platform.core.errors import ApiBusinessError, raise_error
from realmock.platform.models import Resume

logger = logging.getLogger(__name__)


async def _commit_with_retry(
    db: Session, *, reapply: Callable[[], None] | None = None
) -> None:
    """Commit and briefly retry on SQLite ``database is locked``.

    ``reapply`` re-applies in-memory writes after a rollback: ``Session.rollback()``
    expires instances and discards pending changes, so a bare retry would commit
    an empty transaction and silently drop the write it claims to retry.

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
            if reapply is not None:
                reapply()
            await asyncio.sleep(COMMIT_RETRY_DELAY_SECONDS * attempt)


def _review_text_len(analysis: ResumeAnalysis) -> int:
    """Total review-narrative length across the six text fields."""
    texts = (
        analysis.content_review,
        analysis.layout_review,
        analysis.typography_review,
        analysis.overall_narrative,
        analysis.headline,
        analysis.first_impression,
    )
    return sum(len((part or "").strip()) for part in texts)


def _analysis_has_substance(analysis: ResumeAnalysis) -> bool:
    """Reject empty/truncated payloads that would otherwise persist as score 0."""
    return (
        _review_text_len(analysis) >= REVIEW_MIN_TEXT_CHARS
        or len(analysis.dimension_scores) >= REVIEW_MIN_SCORED_DIMENSIONS
    )


def _scoring_needs_recovery(analysis: ResumeAnalysis) -> bool:
    """True when score is 0 and dimension coverage below REVIEW_MIN_SCORED_DIMENSIONS."""
    if analysis.score > 0:
        return False
    return len(analysis.dimension_scores) < REVIEW_MIN_SCORED_DIMENSIONS


def _to_resume_analysis(payload: dict[str, Any], *, locale: str) -> ResumeAnalysis:
    data = normalize_resume_analysis_payload(
        payload if isinstance(payload, dict) else {},
        locale=locale,
    )
    analysis = ResumeAnalysis.model_validate(data)
    if not _analysis_has_substance(analysis):
        logger.warning(
            "Resume analysis lacks substance text_len=%s dims=%s keys=%s",
            _review_text_len(analysis),
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


def resolve_review_locale(resume: Resume) -> str:
    """Plan titles and evaluation language follow the resume body, not the UI locale."""
    return infer_resume_text_locale(resume.raw_text, resume.parsed_profile, resume.filename)


async def _request_score_recovery(
    llm: LLMClient,
    analysis: ResumeAnalysis,
    *,
    locale: str,
    timeout: float | None = None,
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
        "dimension_scores_schema": dimension_scores_schema_fragment(),
    }
    call = chat_json(
        [
            {
                "role": "system",
                "content": score_recovery_system(locale),
            },
            {"role": "user", "content": json.dumps(source, ensure_ascii=False)[:12_000]},
        ],
        temperature=0.1,
        max_tokens=4_000,
    )
    try:
        recovered = await (
            asyncio.wait_for(call, timeout=timeout) if timeout is not None else call
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
    timeout: float | None = None,
) -> ResumeAnalysis:
    recovered = await _request_score_recovery(llm, analysis, locale=locale, timeout=timeout)
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
    if len(repaired.dimension_scores) < REVIEW_MIN_SCORED_DIMENSIONS:
        raise_error("C0002")
    return repaired


async def analyze_resume_with_llm(
    resume: Resume,
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

    if not (resume.raw_text or "").strip():
        file_path = find_resume_file(resume)
        if file_path is None:
            raise_error("A1004")
        extracted = (await extract_resume_text(file_path, resume.file_type, llm, db))[
            :RAW_TEXT_STORE_CHARS
        ]
        try:
            resume.raw_text = extracted
            await _commit_with_retry(
                db, reapply=lambda: setattr(resume, "raw_text", extracted)
            )
        except Exception as e:
            # Same envelope as the analysis write below: a local DB failure is
            # B1001, not an unwrapped OperationalError that would surface as a
            # generic C0001/B0001 with the wrong recovery hint.
            logger.exception("Resume raw text DB write failed")
            db.rollback()
            raise_error("B1001", cause=e)

    review_locale = resolve_review_locale(resume)

    try:
        payload = await run_resume_review(resume, db, llm, locale=review_locale, on_event=on_event)
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
        analysis = await _recover_incomplete_scores(
            llm, analysis, locale=review_locale, timeout=REVIEW_SCORE_RECOVERY_TIMEOUT_SECONDS
        )

    try:
        score = analysis.score
        analysis_json = analysis.model_dump_json()

        def _reapply_analysis_write() -> None:
            resume.score = score
            resume.analysis = analysis_json

        resume.score = score
        resume.analysis = analysis_json
        await _commit_with_retry(db, reapply=_reapply_analysis_write)
    except Exception as e:
        logger.exception("Resume analysis DB write failed")
        db.rollback()
        raise_error("B1001", cause=e)

    return analysis
