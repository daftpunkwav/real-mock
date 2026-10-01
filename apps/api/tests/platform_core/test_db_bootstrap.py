"""Bootstrap tests for realmock.bootstrap.db_bootstrap.

Covers: in-memory backend warnings, empty-domain migrations,
  and test/non-test seeding branches.
Conventions: shared api_engine/engine fixtures; TEST_MODE stubbed.
"""

from __future__ import annotations

from types import SimpleNamespace


class TestBootstrap:
    def test_warn_memory(self, monkeypatch, caplog) -> None:
        import realmock.bootstrap.db_bootstrap as bs

        monkeypatch.setattr(bs, "get_settings", lambda: SimpleNamespace(ws_lease_backend="memory", ratelimit_backend="database"))
        with caplog.at_level("WARNING"):
            bs._warn_inmemory_backends()
        assert any("memory" in r.message for r in caplog.records)
        monkeypatch.setattr(bs, "get_settings", lambda: SimpleNamespace(ws_lease_backend="database", ratelimit_backend="database"))
        bs._warn_inmemory_backends()

    def test_run_migrations_empty_domains(self, api_engine, engine) -> None:
        import realmock.bootstrap.db_bootstrap as bs
        import realmock.platform.models  # noqa: F401

        from realmock.platform.database import ApiBase, SessionsBase

        ApiBase.metadata.create_all(bind=api_engine)
        SessionsBase.metadata.create_all(bind=engine)
        bs._run_migrations(set())

    def test_bootstrap_test_mode_skips_seed(self, monkeypatch, api_engine, engine) -> None:
        import os

        import realmock.bootstrap.db_bootstrap as bs

        monkeypatch.setenv("TEST_MODE", "1")
        called = []
        monkeypatch.setattr(bs, "seed_llm_settings", lambda db: called.append(1))
        bs.bootstrap_databases_and_seed(session_domains=set())
        assert called == []
        bs.shutdown_databases()
        assert os.environ.get("TEST_MODE") == "1"

    def test_bootstrap_non_test_calls_seed(self, monkeypatch, api_engine, engine) -> None:
        import realmock.bootstrap.db_bootstrap as bs
        import realmock.platform.models  # noqa: F401

        from realmock.platform.database import ApiBase, SessionsBase

        ApiBase.metadata.create_all(bind=api_engine)
        SessionsBase.metadata.create_all(bind=engine)
        monkeypatch.setenv("TEST_MODE", "0")
        monkeypatch.setattr(bs, "maybe_migrate_legacy_app_db", lambda: None)
        monkeypatch.setattr(bs, "_warn_inmemory_backends", lambda: None)
        # Record the non-TEST_MODE seed branch: both hooks must actually run.
        called = []
        monkeypatch.setattr(bs, "seed_llm_settings", lambda db: called.append("seed"))
        monkeypatch.setattr(bs, "ensure_pipeline_migrated", lambda db: called.append("pipeline"))
        bs.bootstrap_databases_and_seed(session_domains=set())
        assert called == ["seed", "pipeline"]
        monkeypatch.setenv("TEST_MODE", "1")

    def test_seed_failure_logs_actionable_hint(self, monkeypatch, api_engine, engine, caplog) -> None:
        """A startup seed failure must re-raise (fail fast) but leave a repair path."""
        import pytest

        import realmock.bootstrap.db_bootstrap as bs
        import realmock.platform.models  # noqa: F401

        from realmock.platform.database import ApiBase, SessionsBase

        ApiBase.metadata.create_all(bind=api_engine)
        SessionsBase.metadata.create_all(bind=engine)
        monkeypatch.setenv("TEST_MODE", "0")
        monkeypatch.setattr(bs, "maybe_migrate_legacy_app_db", lambda: None)
        monkeypatch.setattr(bs, "_warn_inmemory_backends", lambda: None)

        def _boom(db):
            raise RuntimeError("seed exploded")

        monkeypatch.setattr(bs, "seed_llm_settings", _boom)
        with caplog.at_level("ERROR"), pytest.raises(RuntimeError):
            bs.bootstrap_databases_and_seed(session_domains=set())
        assert any("locked" in r.message for r in caplog.records)
        monkeypatch.setenv("TEST_MODE", "1")

    def test_migration_failure_logs_actionable_hint(self, monkeypatch, caplog) -> None:
        """A table-create/migration failure gets the same actionable hint."""
        import pytest

        import realmock.bootstrap.db_bootstrap as bs

        monkeypatch.setenv("TEST_MODE", "1")

        def _boom():
            raise RuntimeError("database is locked")

        monkeypatch.setattr(bs, "init_db", _boom)
        with caplog.at_level("ERROR"), pytest.raises(RuntimeError):
            bs.bootstrap_databases_and_seed(session_domains=set())
        assert any("locked" in r.message for r in caplog.records)
        monkeypatch.setenv("TEST_MODE", "1")
