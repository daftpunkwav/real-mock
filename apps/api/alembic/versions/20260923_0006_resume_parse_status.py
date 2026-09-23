"""Resume parse lifecycle columns (parse_status/parse_error + backfill done).

Revision ID: 20260923_0006
Revises: 20260917_0005
Create Date: 2026-09-23
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "20260923_0006"
down_revision: Union[str, None] = "20260917_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from realmock.platform.core.migrate import API_MIGRATIONS, apply_column_migrations

    bind = op.get_bind()
    engine = bind.engine if hasattr(bind, "engine") else bind
    apply_column_migrations(engine, migrations=API_MIGRATIONS)
    # Rows that predate async parsing finished synchronously inside the upload
    # request, so they are done; the column default already covers them.
    bind.execute(text("UPDATE resumes SET parse_status = 'done' WHERE parse_status IS NULL"))


def downgrade() -> None:
    pass
