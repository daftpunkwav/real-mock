"""GitHub integration settings: token save/clear/status/test.

The fine-grained PAT is AES-GCM encrypted at rest (same pattern as LLM
provider keys) and never returned in clear — reads only expose a tail mask.
Connectivity tests accept an unsaved candidate token so the Test button works
before saving.
"""

from __future__ import annotations

import re
import time
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from realmock.platform.capabilities.integrations.github.token_store import GITHUB_CREDENTIAL_KEY
from realmock.platform.core.secrets import decrypt_secret, encrypt_secret
from realmock.platform.models.config_models import IntegrationCredential

#: Accepted PAT families (fine-grained github_pat_ preferred; classic tolerated).
_TOKEN_RE = re.compile(r"^(github_pat_|ghp_|gho_|ghu_|ghs_|ghr_)[A-Za-z0-9_]+$")
_TOKEN_MAX_CHARS = 500
_MASK_KEEP = 4


class GithubTokenSave(BaseModel):
    token: str = Field(..., min_length=1, max_length=_TOKEN_MAX_CHARS)


class GithubTokenTest(BaseModel):
    token: str | None = Field(default=None, max_length=_TOKEN_MAX_CHARS)


def _get_row(db: Session) -> IntegrationCredential | None:
    return (
        db.query(IntegrationCredential)
        .filter(IntegrationCredential.key == GITHUB_CREDENTIAL_KEY)
        .first()
    )


def _mask(token: str) -> str:
    tail = (token or "")[-_MASK_KEEP:] if token else ""
    return f"…{tail}" if tail else ""


def get_github_status(db: Session) -> dict[str, Any]:
    """Configured flag plus tail mask (never the secret)."""
    row = _get_row(db)
    token = decrypt_secret(row.secret_enc) if row and row.secret_enc else ""
    return {"configured": bool(token), "tail": _mask(token or "")}


def save_github_token(db: Session, raw: str) -> dict[str, Any]:
    """Validate, encrypt, and upsert the GitHub token."""
    from realmock.platform.core.errors import ApiBusinessError, get_spec

    text = (raw or "").strip()
    if not text or not _TOKEN_RE.match(text):
        raise ApiBusinessError(
            get_spec("A0007"),
            message="Invalid GitHub token: paste a fine-grained PAT (github_pat_…) or classic token (ghp_…)",
        )
    encrypted = encrypt_secret(text) or ""
    row = _get_row(db)
    if row is None:
        row = IntegrationCredential(key=GITHUB_CREDENTIAL_KEY, secret_enc=encrypted)
        db.add(row)
    else:
        row.secret_enc = encrypted
    db.commit()
    return {"configured": True, "tail": _mask(text)}


def clear_github_token(db: Session) -> dict[str, Any]:
    """Delete the stored GitHub token (env fallback still applies)."""
    row = _get_row(db)
    if row is not None:
        db.delete(row)
        db.commit()
    return {"configured": False, "tail": ""}


async def test_github_token(db: Session, candidate: str | None = None) -> dict[str, Any]:
    """Probe ``GET /rate_limit`` with the candidate, stored, or env token.

    Returns the live quota on success; never echoes any token.
    """
    from realmock.platform.capabilities.integrations.github.client import GitHubClient

    token: str | None = None
    if candidate is not None:
        text = (candidate or "").strip()
        token = text or None
    else:
        row = _get_row(db)
        stored = decrypt_secret(row.secret_enc) if row and row.secret_enc else ""
        token = stored or None
    client = GitHubClient(token=token)
    data = await client.get_rate_limit()
    if isinstance(data, dict) and data.get("error"):
        return {
            "ok": False,
            "message": str(data.get("message") or data.get("error")),
            "status": data.get("status"),
        }
    resources = data.get("resources", {}) if isinstance(data, dict) else {}
    core = resources.get("core", {}) if isinstance(resources, dict) else {}
    return {
        "ok": True,
        "limit": core.get("limit"),
        "remaining": core.get("remaining"),
        "reset_in": max(0, int(core.get("reset", 0)) - time.time())
        if core.get("reset")
        else None,
        "authenticated": bool(client.token),
    }


__all__ = [
    "GithubTokenSave",
    "GithubTokenTest",
    "clear_github_token",
    "get_github_status",
    "save_github_token",
    "test_github_token",
]
