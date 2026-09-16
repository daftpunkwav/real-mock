"""Company question-style brief: setup-preview research endpoint + cache clearing."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from realmock.platform.core.errors import raise_error
from realmock.platform.database import get_api_db, get_sessions_db
from realmock.domains.interview.process.company_brief import (
    clear_company_briefs,
    get_or_create_brief,
)

router = APIRouter()


class CompanyBriefRequest(BaseModel):
    company: str = Field(..., min_length=1, max_length=100)
    role: str = Field(default="", max_length=100)
    level: str = Field(default="", max_length=50)
    interview_type: str = Field(default="", max_length=50)
    locale: str = Field(default="", max_length=10)


@router.post("/company-brief")
async def company_brief(body: CompanyBriefRequest, api_db: Session = Depends(get_api_db), db: Session = Depends(get_sessions_db)) -> dict[str, Any]:
    """Agent-researched brief (style / focus areas / process) for the setup preview.

    Cached per company + role + level + interview type + language; generation
    runs inline (bounded web research) only on a cache miss, so the request can
    take tens of seconds when cold.
    """
    from realmock.platform.capabilities.ai.llm.client import LLMClient

    llm = LLMClient.from_db(api_db)
    if not llm.api_key:
        raise_error("A0006")
    brief = await get_or_create_brief(
        db,
        llm,
        company=body.company,
        role=body.role,
        level=body.level,
        interview_type=body.interview_type,
        locale=body.locale,
    )
    if brief is None:
        raise_error("C0002")
    return brief


@router.delete("/company-briefs")
def delete_company_briefs(db: Session = Depends(get_sessions_db)) -> dict[str, int]:
    """Clear the whole question-style brief cache (settings-page action)."""
    return {"cleared": clear_company_briefs(db)}
