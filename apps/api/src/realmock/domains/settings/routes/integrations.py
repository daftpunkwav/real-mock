"""Third-party integration settings: GitHub credential routes.

Bodies and DB access live in
``realmock.domains.settings.services.github_integration``; this file only
assembles routes. Mounted under the ``/settings`` prefix.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from realmock.domains.settings.services.github_integration import (
    GithubTokenSave,
    GithubTokenTest,
    clear_github_token,
    get_github_status,
    save_github_token,
    test_github_token,
)
from realmock.platform.database import get_db

router = APIRouter()


@router.get("/integrations/github")
def github_status(db: Session = Depends(get_db)) -> dict[str, Any]:
    """GitHub link status: configured flag plus tail mask, never the secret."""
    return get_github_status(db)


@router.post("/integrations/github")
def save_github(body: GithubTokenSave, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Validate, encrypt, and store the GitHub personal access token."""
    return save_github_token(db, body.token)


@router.delete("/integrations/github")
def clear_github(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Delete the stored GitHub token (process-env fallback still applies)."""
    return clear_github_token(db)


@router.post("/integrations/github/test")
async def test_github(body: GithubTokenTest, db: Session = Depends(get_db)) -> dict[str, Any]:
    """Probe ``GET /rate_limit`` with the candidate, stored, or env token.

    Accepts an unsaved candidate so Test works before saving; never echoes tokens.
    """
    return await test_github_token(db, body.token)
