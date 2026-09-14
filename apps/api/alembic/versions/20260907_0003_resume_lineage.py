"""Resume family lineage columns (family_id/version_n + backfill family_id=id, version_n=1).

Revision ID: 20260907_0003
Revises: 20260901_0002
Create Date: 2026-09-07
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "20260907_0003"
down_revision: Union[str, None] = "20260901_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from realmock.platform.core.migrate import API_MIGRATIONS, apply_column_migrations

    bind = op.get_bind()
    engine = bind.engine if hasattr(bind, "engine") else bind
    apply_column_migrations(engine, migrations=API_MIGRATIONS)
    bind.execute(text("UPDATE resumes SET family_id = id WHERE family_id IS NULL OR family_id = 0"))
    bind.execute(text("UPDATE resumes SET version_n = 1 WHERE version_n IS NULL OR version_n < 1"))


def downgrade() -> None:
    pass
