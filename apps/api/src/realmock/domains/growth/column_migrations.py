"""Growth domain sessions.db schema guards and column migrations.

``growth_records`` is created via ``SessionsBase.metadata.create_all``.
Unique index on ``session_id`` is enforced for existing DBs via
:func:`ensure_growth_indexes` (CREATE UNIQUE INDEX IF NOT EXISTS).
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)

SESSIONS_MIGRATIONS: dict[str, list[str]] = {
    # New columns only (ALTER ADD COLUMN). Indexes use ensure_growth_indexes.
}

_UX_SESSION_ID = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_growth_records_session_id ON growth_records (session_id)"
)


def ensure_growth_indexes(engine: Engine) -> None:
    """Idempotently ensure session_id uniqueness on growth_records.

    If duplicate rows already exist, the index creation fails and is logged;
    application-level IntegrityError handling still protects new inserts.
    """
    if engine.url.get_backend_name() != "sqlite":
        return
    try:
        with engine.begin() as conn:
            conn.execute(text(_UX_SESSION_ID))
    except Exception:
        logger.exception(
            "ensure_growth_indexes failed (duplicates may exist); "
            "inserts remain guarded by IntegrityError handling"
        )


__all__ = ["SESSIONS_MIGRATIONS", "ensure_growth_indexes"]
