"""model_profiles: UNIQUE(provider_id, model)

Revision ID: 20260901_0002
Revises: 20260803_0001
Create Date: 2026-09-01
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "20260901_0002"
down_revision: Union[str, None] = "20260803_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_model_profiles_provider_model "
            "ON model_profiles (provider_id, model)"
        )
    )


def downgrade() -> None:
    # Downgrade no-op by design; use DROP INDEX IF EXISTS manually if needed.
    pass
