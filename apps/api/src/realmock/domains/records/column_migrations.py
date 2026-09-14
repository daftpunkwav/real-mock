"""Records domain sessions.db column migrations.

``interview_reports`` is created via ``SessionsBase.metadata.create_all``.
This module holds ALTER statements for future column additions only.
"""

from __future__ import annotations

SESSIONS_MIGRATIONS: dict[str, list[str]] = {
    # New table owned by create_all; keep empty until ALTER is required.
    # "interview_reports": [],
}
