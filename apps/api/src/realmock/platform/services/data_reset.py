"""Wipe all business data across both databases and the filesystem.

Platform-level by design: this module imports no domain packages. The ORM
models register themselves into ``ApiBase`` / ``SessionsBase`` metadata at
bootstrap, so the wipe iterates the shared metadata instead of knowing the
domains — the same trick ``db_split`` uses with its table whitelist.

Scope (user content, not setup):
- files last: the upload directory and growth's ``system_learning.json``
  sidecar (+ lock). Keep files available until both database deletions
  succeed; a later filesystem failure leaves orphaned files for a retry;
- sessions database: every table registered in ``SessionsBase`` metadata
  (interview sessions / turns / processes / reports / company research /
  prep / growth / rate-limit buckets / ws leases);
- api database: only the content tables named in ``API_CONTENT_TABLES`` —
  provider, model, binding, and stage configuration is deliberately kept.

The chroma store (built-in catalog cache) and ``.secret.key`` are not
touched.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy import inspect

from realmock.platform.core.errors import raise_error
from realmock.platform.database import ApiBase, SessionsBase

logger = logging.getLogger(__name__)

#: Api-database tables that hold user content (everything else stays).
API_CONTENT_TABLES: tuple[str, ...] = ("resumes", "user_profiles")

#: Growth's JSON sidecar, colocated with the databases under platform/data
#: (same resolution as the growth learning service: PLATFORM_ROOT/data).
LEARNING_FILE_NAME = "system_learning.json"


def _existing_tables(engine: Any, metadata_tables: set[str]) -> list[str]:
    """Tables present both in the live database and the given metadata subset."""
    names = set(inspect(engine).get_table_names())
    return sorted(metadata_tables & names)


def _clear_uploads(uploads_dir: Path) -> int:
    """Delete files inside the upload directory; keep the directory itself."""
    if not uploads_dir.exists():
        return 0
    removed = 0
    for child in sorted(uploads_dir.iterdir()):
        if child.is_file():
            child.unlink(missing_ok=True)
            removed += 1
    return removed


def _clear_learning_sidecar() -> bool:
    """Remove the growth learning JSON (+ lock); the service recreates defaults."""
    from realmock.platform.config import PLATFORM_ROOT

    data_dir = PLATFORM_ROOT / "data"
    removed = False
    for candidate in (data_dir / LEARNING_FILE_NAME, data_dir / f"{LEARNING_FILE_NAME}.lock"):
        if candidate.is_file():
            candidate.unlink(missing_ok=True)
            removed = True
    return removed


def _clear_sessions_db() -> dict[str, int]:
    from realmock.platform.database import get_sessions_engine

    engine = get_sessions_engine()
    cleared: dict[str, int] = {}
    with engine.begin() as conn:
        for name in _existing_tables(engine, set(SessionsBase.metadata.tables)):
            table = SessionsBase.metadata.tables[name]
            result = conn.execute(table.delete())
            cleared[name] = int(result.rowcount or 0)
    return cleared


def _clear_api_db() -> dict[str, int]:
    from realmock.platform.database import get_api_engine

    engine = get_api_engine()
    wanted = set(API_CONTENT_TABLES)
    cleared: dict[str, int] = {}
    with engine.begin() as conn:
        for name in _existing_tables(engine, wanted):
            table = ApiBase.metadata.tables[name]
            result = conn.execute(table.delete())
            cleared[name] = int(result.rowcount or 0)
    return cleared


def clear_all_business_data() -> dict[str, Any]:
    """Wipe user content everywhere; returns per-area counts for the response."""
    from realmock.platform.config import get_settings

    settings = get_settings()
    # These databases commit independently. Report a partial wipe explicitly
    # if the second deletion fails; retain files and allow an idempotent retry.
    sessions_tables = _clear_sessions_db()
    try:
        api_tables = _clear_api_db()
    except Exception as exc:
        logger.exception(
            "Data deletion partially completed; sessions cleared: %s", str(sessions_tables)
        )
        raise_error("B1003", cause=exc)
    upload_files = _clear_uploads(Path(settings.upload_dir))
    learning_reset = _clear_learning_sidecar()
    return {
        "sessions_tables": sessions_tables,
        "api_tables": api_tables,
        "upload_files": upload_files,
        "learning_reset": learning_reset,
    }
