"""ASGI lifespan tests for realmock.asgi.

Covers: health/CORS/secret policies, shutdown swallowing, contract
  wiring guards, and lifespan bootstrap/dispose branches.
Conventions: TestClient for health; monkeypatched wiring for guards.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from realmock.platform.core.ratelimit import reset_rate_limit


class TestAsgiPolicies:
    def test_health_and_cors(self) -> None:
        reset_rate_limit()
        try:
            with TestClient(__import__("realmock.asgi", fromlist=["app"]).app) as client:
                assert client.get("/health").json()["status"] == "ok"
        finally:
            reset_rate_limit()

    def test_cors_wildcard(self) -> None:
        import realmock.asgi as asgi

        with pytest.raises(RuntimeError, match="CORS"):
            asgi._check_cors_policy(SimpleNamespace(cors_origin_list=["*"], is_prod=True))
        asgi._check_cors_policy(SimpleNamespace(cors_origin_list=["*"], is_prod=False))
        asgi._check_cors_policy(SimpleNamespace(cors_origin_list=["http://x"], is_prod=True))

    def test_secret_policy(self, monkeypatch) -> None:
        import realmock.asgi as asgi

        monkeypatch.setattr("realmock.platform.core.secrets.validate_master_key_env", lambda: "missing")
        # prod + missing -> raise; non-prod passes
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            asgi._check_secret_key_policy(SimpleNamespace(is_prod=True))
        asgi._check_secret_key_policy(SimpleNamespace(is_prod=False))

    def test_shutdown_engine_swallow(self, monkeypatch) -> None:
        import realmock.asgi as asgi

        monkeypatch.setattr(asgi, "dispose_all_engines", lambda: (_ for _ in ()).throw(RuntimeError("x")))
        asgi._shutdown_engine()

    def test_wire_contracts_guard(self, monkeypatch) -> None:
        import realmock.asgi as asgi
        import realmock.platform.contracts.lifecycle_hooks as lh
        import realmock.platform.contracts.session_catalog as sc
        import realmock.platform.contracts.session_score as ss

        # Neutralize real registrations so the empty-port guards trigger
        # (register_interview/ensure_growth are imported inside _wire -> patch
        # sources; the two ingest registers are asgi module globals -> patch there).
        monkeypatch.setattr("realmock.domains.interview.process.catalog.register_interview_session_catalog", lambda: None)
        monkeypatch.setattr(asgi, "register_records_lifecycle_handlers", lambda: None)
        monkeypatch.setattr(asgi, "register_growth_lifecycle_handlers", lambda: None)
        monkeypatch.setattr("realmock.domains.growth.column_migrations.ensure_growth_indexes", lambda e: None)
        monkeypatch.setattr(sc, "_catalog", sc._EmptySessionCatalog())
        monkeypatch.setattr(ss, "_projection", ss._NoopScoreProjection())
        monkeypatch.setattr(lh, "_on_interview_finished", None)
        monkeypatch.setattr(lh, "_on_report_summary", None)
        monkeypatch.setattr(lh, "_system_insights_provider", lambda: True)
        # catalog missing -> RuntimeError for catalog port
        with pytest.raises(RuntimeError, match="catalog"):
            asgi._wire_platform_contracts()

    @pytest.mark.asyncio
    async def test_lifespan_non_test_and_dispose(self, monkeypatch) -> None:
        import asyncio as _aio
        import realmock.asgi as asgi

        monkeypatch.setenv("TEST_MODE", "0")
        monkeypatch.setattr(asgi, "_bootstrap_db_and_seed", lambda: None)
        monkeypatch.setattr("realmock.domains.interview.startup.ensure_rag_index", lambda: _aio.sleep(0))
        monkeypatch.setattr(asgi, "ensure_rag_index", lambda: _aio.sleep(0))
        monkeypatch.setattr(asgi, "_shutdown_engine", lambda: None)
        app = MagicMock()
        async with asgi.lifespan(app):
            pass

    @pytest.mark.asyncio
    async def test_lifespan_shutdown_dispose_branch(self, monkeypatch) -> None:
        import asyncio as _aio
        import realmock.asgi as asgi

        monkeypatch.setenv("TEST_MODE", "0")
        monkeypatch.setattr(asgi, "_bootstrap_db_and_seed", lambda: None)
        monkeypatch.setattr(asgi, "ensure_rag_index", lambda: _aio.sleep(0))
        monkeypatch.setattr(asgi, "get_settings", lambda: SimpleNamespace(env="dev", is_prod=False))
        calls = []
        monkeypatch.setattr(asgi, "_shutdown_engine", lambda: calls.append(1))
        app = MagicMock()
        async with asgi.lifespan(app):
            pass
        assert calls == [1]

    def test_wire_each_guard(self, monkeypatch) -> None:
        import realmock.asgi as asgi
        import realmock.platform.contracts.lifecycle_hooks as lh
        import realmock.platform.contracts.session_catalog as sc
        import realmock.platform.contracts.session_score as ss

        monkeypatch.setattr("realmock.domains.interview.process.catalog.register_interview_session_catalog", lambda: None)
        monkeypatch.setattr(asgi, "register_records_lifecycle_handlers", lambda: None)
        monkeypatch.setattr(asgi, "register_growth_lifecycle_handlers", lambda: None)
        monkeypatch.setattr("realmock.domains.growth.column_migrations.ensure_growth_indexes", lambda e: None)

        class _GoodCatalog(sc._EmptySessionCatalog):
            pass

        class _GoodProj:
            def apply_overall_score(self, db, sid, score):
                pass

        # score guard
        monkeypatch.setattr(sc, "_catalog", _GoodCatalog())
        monkeypatch.setattr(ss, "_projection", ss._NoopScoreProjection())
        monkeypatch.setattr(lh, "_system_insights_provider", lambda: True)
        monkeypatch.setattr(lh, "_on_interview_finished", lambda p: None)
        monkeypatch.setattr(lh, "_on_report_summary", lambda p: None)
        with pytest.raises(RuntimeError, match="score"):
            asgi._wire_platform_contracts()
        # insights guard (neutralize the unconditional provider wiring)
        monkeypatch.setattr(ss, "_projection", _GoodProj())
        monkeypatch.setattr("realmock.platform.contracts.lifecycle_hooks.set_system_insights_provider", lambda p: None)
        monkeypatch.setattr(lh, "_system_insights_provider", None)
        with pytest.raises(RuntimeError, match="insights"):
            asgi._wire_platform_contracts()
        # finished guard
        monkeypatch.setattr(lh, "_system_insights_provider", lambda: True)
        monkeypatch.setattr(lh, "_on_interview_finished", None)
        with pytest.raises(RuntimeError, match="interview-finished"):
            asgi._wire_platform_contracts()
        # report guard
        monkeypatch.setattr(lh, "_on_interview_finished", lambda p: None)
        monkeypatch.setattr(lh, "_on_report_summary", None)
        with pytest.raises(RuntimeError, match="report-summary"):
            asgi._wire_platform_contracts()
