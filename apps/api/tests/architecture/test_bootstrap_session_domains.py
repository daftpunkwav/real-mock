"""Bootstrap domain registration: isolated processes must not load unrelated business ORMs."""

from __future__ import annotations

import sys

import pytest


def test_register_empty_domains_skips_business_packages(monkeypatch: pytest.MonkeyPatch) -> None:
    """session_domains=() registers platform tables only (no prep/interview/records/growth)."""
    for name in list(sys.modules):
        if name.startswith(
            (
                "realmock.domains.prep.models",
                "realmock.domains.interview.models",
                "realmock.domains.records.models",
                "realmock.domains.growth.models",
            )
        ):
            monkeypatch.delitem(sys.modules, name, raising=False)

    imported: list[str] = []
    real_import = __import__

    def tracking_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in (
            "realmock.domains.prep.models",
            "realmock.domains.interview.models",
            "realmock.domains.records.models",
            "realmock.domains.growth.models",
        ) or name.startswith(
            (
                "realmock.domains.prep.models.",
                "realmock.domains.interview.models.",
                "realmock.domains.records.models.",
                "realmock.domains.growth.models.",
            )
        ):
            imported.append(name)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", tracking_import)

    from realmock.bootstrap.sessions_orm import register_sessions_domain_models

    register_sessions_domain_models(())
    assert imported == []


def test_register_prep_only_skips_interview(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(sys.modules):
        if name.startswith("realmock.domains.interview.models"):
            monkeypatch.delitem(sys.modules, name, raising=False)

    imported: list[str] = []
    real_import = __import__

    def tracking_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "realmock.domains.interview.models" or name.startswith("realmock.domains.interview.models."):
            imported.append(name)
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", tracking_import)

    from realmock.bootstrap.sessions_orm import register_sessions_domain_models

    register_sessions_domain_models(("prep",))
    assert imported == []


def test_register_unknown_domain_raises() -> None:
    from realmock.bootstrap.sessions_orm import register_sessions_domain_models

    with pytest.raises(ValueError, match="Unknown sessions domain"):
        register_sessions_domain_models(("nope",))


def test_sessions_column_migrations_follow_domains() -> None:
    """Column migration map is assembled by domain: empty= {}; single= own tables; None= all."""
    from realmock.bootstrap.sessions_orm import sessions_column_migrations

    assert sessions_column_migrations(()) == {}

    prep_only = sessions_column_migrations(("prep",))
    assert set(prep_only) == {"prep_sessions"}

    interview_only = sessions_column_migrations(("interview",))
    assert set(interview_only) == {"interview_sessions"}

    records_only = sessions_column_migrations(("records",))
    assert set(records_only) == set()  # create_all owns new table; no ALTER yet

    growth_only = sessions_column_migrations(("growth",))
    assert set(growth_only) == set()  # create_all owns new table; no ALTER yet

    all_domains = sessions_column_migrations(None)
    assert set(all_domains) == {"prep_sessions", "interview_sessions"}


def test_sessions_column_migrations_unknown_domain_raises() -> None:
    from realmock.bootstrap.sessions_orm import sessions_column_migrations

    with pytest.raises(ValueError, match="Unknown sessions domain"):
        sessions_column_migrations(("nope",))
