"""sessions.db domain registration (composition root): ORM + column migrations.

Business models must be imported before ``SessionsBase.metadata.create_all``,
but must not live in ``platform.database`` (no platform -> domain imports).
Column DDL lives in each domain's ``column_migrations`` and is assembled here.
"""

from __future__ import annotations

from collections.abc import Collection
from typing import Literal

SessionDomain = Literal["prep", "interview", "records", "growth"]
_ALL_DOMAINS: frozenset[str] = frozenset({"prep", "interview", "records", "growth"})


def _normalize_domains(domains: Collection[str] | None) -> frozenset[str]:
    """Normalize domain names: ``None`` = all session domains; reject unknown."""
    wanted = _ALL_DOMAINS if domains is None else frozenset(domains)
    unknown = wanted - _ALL_DOMAINS
    if unknown:
        raise ValueError(f"Unknown sessions domain: {sorted(unknown)}")
    return wanted


def register_platform_sessions_models() -> None:
    """Register platform sessions.db tables (rate-limit buckets) only."""
    import realmock.platform.models.rate_limit_bucket  # noqa: F401


def register_sessions_domain_models(
    domains: Collection[str] | None = None,
) -> None:
    """Register selected session-domain tables onto ``SessionsBase.metadata``.

    Args:
        domains:
            - ``None``: register all (prep + interview + records + growth).
            - empty: platform tables only.
            - subset: register those domains only.
    """
    register_platform_sessions_models()
    wanted = _normalize_domains(domains)
    if "prep" in wanted:
        import realmock.domains.prep.models  # noqa: F401
    if "interview" in wanted:
        import realmock.domains.interview.models  # noqa: F401
    if "records" in wanted:
        import realmock.domains.records.models  # noqa: F401
    if "growth" in wanted:
        import realmock.domains.growth.models  # noqa: F401


def sessions_column_migrations(
    domains: Collection[str] | None = None,
) -> dict[str, list[str]]:
    """Assemble sessions.db column migration map by domain (lazy imports)."""
    wanted = _normalize_domains(domains)
    merged: dict[str, list[str]] = {}
    if "prep" in wanted:
        from realmock.domains.prep.column_migrations import SESSIONS_MIGRATIONS as PREP_MIGRATIONS

        merged.update(PREP_MIGRATIONS)
    if "interview" in wanted:
        from realmock.domains.interview.column_migrations import (
            SESSIONS_MIGRATIONS as INTERVIEW_MIGRATIONS,
        )

        merged.update(INTERVIEW_MIGRATIONS)
    if "records" in wanted:
        from realmock.domains.records.column_migrations import (
            SESSIONS_MIGRATIONS as RECORDS_MIGRATIONS,
        )

        merged.update(RECORDS_MIGRATIONS)
    if "growth" in wanted:
        from realmock.domains.growth.column_migrations import (
            SESSIONS_MIGRATIONS as GROWTH_MIGRATIONS,
        )

        merged.update(GROWTH_MIGRATIONS)
    return merged


__all__ = [
    "SessionDomain",
    "register_platform_sessions_models",
    "register_sessions_domain_models",
    "sessions_column_migrations",
]
