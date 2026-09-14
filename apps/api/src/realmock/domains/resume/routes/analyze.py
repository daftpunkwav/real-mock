"""Resume deep-review HTTP handlers.

Responsibilities:
- Parse optional JSON body (empty body → default locale)
- Enforce the in-process analysis slot cap
- JSON ``POST /analyze`` for compatibility
- SSE ``POST /analyze/stream`` for live Agent plan / tool / thinking events

Persistence lives in the store; the slot cap lives in ``analyze_slots``.
This module must not query SQLAlchemy models directly.
"""

from __future__ import annotations

import json
import logging

from fastapi import Depends, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session

from realmock.domains.resume.schemas.limits import SSE_HEARTBEAT_SECONDS
from realmock.domains.resume.schemas.request import ResumeAnalyzeRequest
from realmock.domains.resume.services import analyze_slots, store
from realmock.domains.resume.services.analysis import analyze_resume_with_llm
from realmock.platform.core.errors import ApiBusinessError, raise_error
from realmock.platform.core.security import redact_api_key
from realmock.platform.core.sse import (
    QueuePut,
    pump_queue_to_sse,
    sse_error_event,
    sse_streaming_response,
)
from realmock.platform.database import get_db

logger = logging.getLogger(__name__)

_SSE_ERR_GENERIC = "Deep review failed, please try again later"


async def _parse_analyze_body(request: Request) -> ResumeAnalyzeRequest:
    """Parse optional JSON body; missing/empty body → default ``zh-CN``.

    The shared frontend ``request()`` always sends ``Content-Type: application/json``
    even when the body is empty, so we cannot rely on FastAPI's optional Body
    default alone without risking 422 on empty payloads.
    """
    raw = await request.body()
    if not raw or not raw.strip():
        return ResumeAnalyzeRequest()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise_error("A0001", cause=e)
    if data is None or data == {}:
        return ResumeAnalyzeRequest()
    if not isinstance(data, dict):
        raise_error("A0001")
    try:
        return ResumeAnalyzeRequest.model_validate(data)
    except ValidationError as e:
        raise_error("A0001", cause=e)


def _error_event(exc: BaseException) -> dict:
    return sse_error_event(exc, message=_SSE_ERR_GENERIC)


async def analyze_resume(
    resume_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    row = store.get_row(db, resume_id)
    if not row:
        raise_error("A1005")
    body = await _parse_analyze_body(request)
    await analyze_slots.acquire_slot()
    try:
        return await analyze_resume_with_llm(row, db, locale=body.locale)
    finally:
        await analyze_slots.release_slot()


async def analyze_resume_stream(
    resume_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """SSE: plan / tool_step / thinking / notice / done{analysis} / error."""
    row = store.get_row(db, resume_id)
    if not row:
        raise_error("A1005")
    body = await _parse_analyze_body(request)

    async def run(put: QueuePut) -> None:
        acquired = False
        try:
            await analyze_slots.acquire_slot()
            acquired = True
            analysis = await analyze_resume_with_llm(
                row, db, locale=body.locale, on_event=put
            )
            await put(
                {"type": "done", "analysis": analysis.model_dump(mode="json")}
            )
        except Exception as exc:
            if not isinstance(exc, ApiBusinessError):
                logger.exception(
                    "Resume analyze stream failed id=%s: %s",
                    resume_id,
                    redact_api_key(str(exc)),
                )
            await put(_error_event(exc))
        finally:
            if acquired:
                await analyze_slots.release_slot()
            await put(None)

    return sse_streaming_response(
        pump_queue_to_sse(request, run, heartbeat_seconds=SSE_HEARTBEAT_SECONDS)
    )
