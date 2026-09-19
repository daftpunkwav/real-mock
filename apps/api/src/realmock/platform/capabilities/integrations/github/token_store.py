"""Stored integration credentials (platform-internal token access).

Reads the ``integration_credentials`` table directly so the GitHub client
stays domain-free: settings services write through this same table, agents
only ever see a boolean/tail mask. All helpers degrade to empty on any
failure — a broken credential store must never break client construction.
"""

from __future__ import annotations

import logging
from typing import cast

from sqlalchemy.orm import Session

from realmock.platform.core.secrets import decrypt_secret
from realmock.platform.database import api_db_session
from realmock.platform.models.config_models import IntegrationCredential

logger = logging.getLogger(__name__)

#: Credential key for the GitHub personal access token.
GITHUB_CREDENTIAL_KEY = "github"


def _read_secret(key: str, db: Session | None = None) -> str:
    """Decrypt the stored secret for ``key`` (empty string when absent/broken)."""
    try:
        if db is not None:
            row = db.query(IntegrationCredential).filter(IntegrationCredential.key == key).first()
            # decrypt_secret only yields None for falsy input, excluded by the guard.
            return cast("str", decrypt_secret(row.secret_enc)) if row and row.secret_enc else ""
        with api_db_session() as session:
            row = (
                session.query(IntegrationCredential)
                .filter(IntegrationCredential.key == key)
                .first()
            )
            return cast("str", decrypt_secret(row.secret_enc)) if row and row.secret_enc else ""
    except Exception as e:
        logger.warning("Integration credential read failed key=%s: %s", key, e)
        return ""


def read_stored_token(key: str = GITHUB_CREDENTIAL_KEY, db: Session | None = None) -> str:
    """Stored token for ``key`` (empty when unconfigured). Never raises."""
    return _read_secret(key, db)


def has_stored_token(key: str = GITHUB_CREDENTIAL_KEY, db: Session | None = None) -> bool:
    """Whether a non-empty token is stored for ``key``. Never raises."""
    return bool(_read_secret(key, db))


__all__ = ["GITHUB_CREDENTIAL_KEY", "has_stored_token", "read_stored_token"]
