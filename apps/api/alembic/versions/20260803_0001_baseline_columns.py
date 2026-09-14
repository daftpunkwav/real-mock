"""baseline: backfill historical columns (idempotent)

Revision ID: 20260803_0001
Revises:
Create Date: 2026-08-03

The original implementation referenced the global migration union (``MIGRATIONS``, since removed when migrations were split by database);
now pass ``API_MIGRATIONS`` explicitly: this chain manages only api.db, and upgrade safely skips existing columns.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260803_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from realmock.platform.core.migrate import API_MIGRATIONS, apply_column_migrations

    bind = op.get_bind()
    # Either Engine or Connection is accepted: apply uses begin()/inspect.
    engine = bind.engine if hasattr(bind, "engine") else bind
    apply_column_migrations(engine, migrations=API_MIGRATIONS)


def downgrade() -> None:
    # Dropping columns in SQLite is expensive; the baseline revision does not support automatic downgrade.
    pass
