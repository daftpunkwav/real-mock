"""Alembic environment: manages only the api-domain schema (Settings.api_database_url).

metadata covers tables attached to ``ApiBase`` in ``realmock.platform.models`` (profile/resume/settings);
sessions-domain tables (interview/Prep/lease/rate-limit bucket, attached to ``SessionsBase``) are not managed by this chain
and are created at startup by ``SessionsBase.metadata.create_all``.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from realmock.platform.config import get_settings
from realmock.platform.database import ApiBase

# Ensure all models based on ApiBase are registered in metadata
import realmock.platform.models  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = ApiBase.metadata


def get_url() -> str:
    return get_settings().api_database_url


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
