"""``realmock.platform.config.Settings`` cross-field validation.

The legacy ``DATABASE_URL`` alias maps onto the sessions database. It must be
read from the resolved field (which pydantic-settings also populates from the
``platform/.env`` file), not from ``os.environ``: pydantic-settings parses the
env file itself and never exports it into the process environment, so an
env-file value used to be silently ignored while ``database_url`` (read by the
interview RAG store) still pointed at it.
"""

from __future__ import annotations

from pathlib import Path


def _settings(**kwargs):
    from realmock.platform.config import Settings

    # The process environment must not leak into these checks: the test
    # session exports DATABASE_URL / API_DATABASE_URL / SESSIONS_DATABASE_URL,
    # and a developer's platform/.env may exist. Every case states its own
    # source explicitly (env file or constructor argument).
    return Settings(_env_file=None, **kwargs)


def _clear_db_env(monkeypatch) -> None:
    for name in ("DATABASE_URL", "API_DATABASE_URL", "SESSIONS_DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)


def test_database_url_from_env_file_overrides_sessions_database(
    tmp_path: Path, monkeypatch
) -> None:
    """A DATABASE_URL set only in the env file still maps onto the sessions DB."""
    _clear_db_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text("DATABASE_URL=sqlite:////tmp/legacy-from-dotenv.db\n", encoding="utf-8")

    from realmock.platform.config import Settings

    settings = Settings(_env_file=str(env_file))

    assert settings.database_url == "sqlite:////tmp/legacy-from-dotenv.db"
    assert settings.sessions_database_url == settings.database_url


def test_env_file_without_database_url_keeps_configured_sessions_database(
    tmp_path: Path, monkeypatch
) -> None:
    """The alias only rewrites the sessions URL when it is actually provided."""
    _clear_db_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SESSIONS_DATABASE_URL=sqlite:////tmp/explicit-sessions.db\n", encoding="utf-8"
    )

    from realmock.platform.config import Settings

    settings = Settings(_env_file=str(env_file))

    assert settings.sessions_database_url == "sqlite:////tmp/explicit-sessions.db"
    # ``database_url`` is only the legacy alias; it is not rewritten backwards.
    assert settings.database_url == Settings.model_fields["database_url"].default


def test_process_env_database_url_still_overrides_sessions_database(monkeypatch) -> None:
    """The documented process-environment alias keeps its previous behavior."""
    _clear_db_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "sqlite:////tmp/legacy-from-env.db")

    settings = _settings()

    assert settings.database_url == "sqlite:////tmp/legacy-from-env.db"
    assert settings.sessions_database_url == settings.database_url


def test_database_url_restating_the_default_does_not_reset_explicit_sessions_url(
    monkeypatch,
) -> None:
    """An explicit SESSIONS_DATABASE_URL survives a DATABASE_URL that restates the default."""
    _clear_db_env(monkeypatch)

    from realmock.platform.config import PLATFORM_ROOT, Settings

    default_sessions = Settings.model_fields["sessions_database_url"].default
    assert default_sessions.startswith("sqlite:///")
    assert str(PLATFORM_ROOT) in default_sessions

    settings = _settings(
        database_url=default_sessions,
        sessions_database_url="sqlite:////tmp/keep-this-sessions.db",
    )

    assert settings.sessions_database_url == "sqlite:////tmp/keep-this-sessions.db"
