"""Provider optional reference info (llm_providers.website_url / notes).

Revision ID: 20260917_0005
Revises: 20260916_0004
Create Date: 2026-09-17
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260917_0005"
down_revision: Union[str, None] = "20260916_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from realmock.platform.core.migrate import API_MIGRATIONS, apply_column_migrations

    bind = op.get_bind()
    engine = bind.engine if hasattr(bind, "engine") else bind
    apply_column_migrations(engine, migrations=API_MIGRATIONS)


def downgrade() -> None:
    pass
