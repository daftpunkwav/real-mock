"""Wipe all business data across both databases and the filesystem.

Platform-level by design: this module imports no domain packages. The ORM
models register themselves into ``ApiBase`` / ``SessionsBase`` metadata at
bootstrap, so the wipe iterates the shared metadata instead of knowing the
domains — the same trick ``db_split`` uses with its table whitelist.

Scope (user content, not setup):
- sessions database: every table registered in ``SessionsBase`` metadata
  (interview sessions / turns / processes / reports / prep / growth / leases);
- api database: only the content tables named in ``API_CONTENT_TABLES`` —
  provider, model, binding, and stage configuration is deliberately kept;
- upload directory: resume files;
- data directory: growth's ``system_learning.json`` sidecar (the chroma
  store is derived cache from the built-in catalog and is left alone).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy import inspect

from realmock.platform.database import ApiBase, SessionsBase

logger = logging.getLogger(__name__)

#: Api-database tables that hold user content (everything else stays).
API_CONTENT_TABLES: tuple[str, ...] = ("resumes", "user_profiles")

#: Growth's JSON sidecar, colocated with the databases under platform/data.
LEARNING_FILE_NAME = "system_learning.json"


def _existing_tables(engine: Any, metadata_tables: set[str]) -> list[str]:
    """Tables present both in the live database and the given metadata subset."""
    names = set(inspect(engine).get_table_names())
    return sorted(metadata_tables & names)


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


def _clear_learning_sidecar(data_dir: Path) -> bool:
    """Remove the growth learning JSON (+ lock); the service recreates defaults."""
    removed = False
    for candidate in (data_dir / LEARNING_FILE_NAME, data_dir / f"{LEARNING_FILE_NAME}.lock"):
        if candidate.is_file():
            candidate.unlink(missing_ok=True)
            removed = True
    return removed


def clear_all_business_data() -> dict[str, Any]:
    """Wipe user content everywhere; returns per-area counts for the response."""
    from realmock.platform.config import get_settings

    settings = get_settings()
    sessions_db_path = Path(str(settings.sessions_database_url).replace("sqlite:///", ""))
    data_dir = sessions_db_path.parent if not str(sessions_db_path).startswith(":") else None

    return {
        "sessions_tables": _clear_sessions_db(),
        "api_tables": _clear_api_db(),
        "upload_files": _clear_uploads(Path(settings.upload_dir)),
        "learning_reset": _clear_learning_sidecar(data_dir) if data_dir is not None else False,
    }
