"""Application composition root (registration during startup, non-business logic)."""

from realmock.bootstrap.sessions_orm import (
    register_platform_sessions_models,
    register_sessions_domain_models,
    sessions_column_migrations,
)

__all__ = [
    "register_platform_sessions_models",
    "register_sessions_domain_models",
    "sessions_column_migrations",
]
