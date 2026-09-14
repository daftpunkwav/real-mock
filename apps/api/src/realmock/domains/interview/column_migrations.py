"""Interview-domain sessions.db column backfill DDL.

Schema ownership stays in the business package: this module only declares
``interview_sessions`` ALTER statements. Composition root
``realmock.bootstrap.sessions_orm.sessions_column_migrations`` assembles them for
:func:`realmock.platform.core.migrate.apply_column_migrations`.
"""

from __future__ import annotations

SESSIONS_MIGRATIONS: dict[str, list[str]] = {
    "interview_sessions": [
        "ALTER TABLE interview_sessions ADD COLUMN avatar_id VARCHAR(50) DEFAULT 'professional_male'",
        "ALTER TABLE interview_sessions ADD COLUMN scene_id VARCHAR(50) DEFAULT 'meeting_room'",
        "ALTER TABLE interview_sessions ADD COLUMN token_usage INTEGER DEFAULT 0",
        "ALTER TABLE interview_sessions ADD COLUMN access_token VARCHAR(64) DEFAULT ''",
        "ALTER TABLE interview_sessions ADD COLUMN ai_overrides TEXT DEFAULT '{}'",
        "ALTER TABLE interview_sessions ADD COLUMN ledger TEXT DEFAULT '{}'",
        "ALTER TABLE interview_sessions ADD COLUMN process_id INTEGER",
        "ALTER TABLE interview_sessions ADD COLUMN round_no INTEGER",
        "ALTER TABLE interview_sessions ADD COLUMN result VARCHAR(20)",
        "ALTER TABLE interview_sessions ADD COLUMN plan TEXT",
        "ALTER TABLE interview_sessions ADD COLUMN plan_status VARCHAR(20) DEFAULT ''",
    ],
    "interview_processes": [
        "ALTER TABLE interview_processes ADD COLUMN round_plan TEXT DEFAULT '{}'",
        "ALTER TABLE interview_processes ADD COLUMN round_plan_status VARCHAR(20) DEFAULT ''",
    ],
}
