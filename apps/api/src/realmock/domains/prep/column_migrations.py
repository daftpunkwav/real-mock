"""Column-completion manifest for prep-domain sessions.db.

The business package owns the schema: this module declares only the column-completion DDL for ``prep_sessions``.
The composition root ``realmock.bootstrap.db_bootstrap.bootstrap_databases_and_seed`` assembles it by domain;
the shared platform layer owns no session-business DDL (removing this package does not affect platform migration code).
"""

from __future__ import annotations

SESSIONS_MIGRATIONS: dict[str, list[str]] = {
    "prep_sessions": [
        "ALTER TABLE prep_sessions ADD COLUMN status VARCHAR(20) DEFAULT 'active'",
        "ALTER TABLE prep_sessions ADD COLUMN access_token VARCHAR(64) DEFAULT ''",
        "ALTER TABLE prep_sessions ADD COLUMN updated_at DATETIME DEFAULT NULL",
        "ALTER TABLE prep_sessions ADD COLUMN prompt_tokens INTEGER DEFAULT 0",
        "ALTER TABLE prep_sessions ADD COLUMN completion_tokens INTEGER DEFAULT 0",
        "ALTER TABLE prep_sessions ADD COLUMN cached_tokens INTEGER DEFAULT 0",
        "ALTER TABLE prep_sessions ADD COLUMN linked_session_id INTEGER DEFAULT NULL",
        "ALTER TABLE prep_sessions ADD COLUMN summary VARCHAR(100) DEFAULT ''",
        "ALTER TABLE prep_sessions ADD COLUMN message_count INTEGER DEFAULT 0",
    ],
}

__all__ = [
    "SESSIONS_MIGRATIONS",
]
