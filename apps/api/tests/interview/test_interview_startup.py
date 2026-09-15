"""Interview startup tests for src/realmock/domains/interview/startup.py and src/realmock/domains/interview/column_migrations.py.

Covers: SESSION_DOMAINS, wire_session_catalog, ensure_rag_index branches, SESSIONS_MIGRATIONS shape
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from realmock.domains.interview import column_migrations as cm
from realmock.domains.interview import startup as startup_mod


def _valid_plan_dict(n=8):
    return {
        "round_note": "Round 1",
        "source": "agent",
        "language": "zh",
        "opening": {"style": "identity_confirm", "note": ""},
        "steps": [
            {"title": f"Step {i}", "focus": f"focus {i}", "max_questions": 2}
            for i in range(n)
        ],
    }


















@contextmanager
def _sessions_ctx(db_obj):
    yield db_obj






























# ---- startup / migrations ----

def test_session_domains_declared() -> None:
    assert startup_mod.SESSION_DOMAINS == ("interview",)


def test_wire_session_catalog_registers(monkeypatch) -> None:
    seen: dict = {}
    monkeypatch.setattr(
        "realmock.domains.interview.process.catalog.register_interview_session_catalog",
        lambda: seen.update({"ok": True}),
    )
    startup_mod.wire_session_catalog()
    assert seen.get("ok") is True


@pytest.mark.asyncio
async def test_ensure_rag_index_test_mode_skips(monkeypatch) -> None:
    monkeypatch.setenv("TEST_MODE", "1")
    with patch("realmock.domains.interview.startup.ApiSessionLocal") as mock_local:
        await startup_mod.ensure_rag_index()
        mock_local.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_rag_index_no_key_skips(monkeypatch) -> None:
    monkeypatch.setenv("TEST_MODE", "0")
    from unittest.mock import MagicMock

    fake_db = MagicMock()
    fake_llm = SimpleNamespace(api_key="")
    monkeypatch.setattr(startup_mod, "ApiSessionLocal", lambda: fake_db)
    with patch(
        "realmock.platform.capabilities.ai.llm.client.LLMClient.from_db", return_value=fake_llm
    ):
        await startup_mod.ensure_rag_index()
        fake_db.close.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_rag_index_builds(monkeypatch) -> None:
    monkeypatch.setenv("TEST_MODE", "0")
    from unittest.mock import AsyncMock, MagicMock

    fake_db = MagicMock()
    fake_llm = SimpleNamespace(api_key="k")
    fake_rag = SimpleNamespace(ensure_index=AsyncMock())
    monkeypatch.setattr(startup_mod, "ApiSessionLocal", lambda: fake_db)
    with (
        patch(
            "realmock.platform.capabilities.ai.llm.client.LLMClient.from_db",
            return_value=fake_llm,
        ),
        patch(
            "realmock.domains.interview.capabilities.rag.company_rag.CompanyKnowledgeRAG",
            return_value=fake_rag,
        ),
    ):
        await startup_mod.ensure_rag_index()
        fake_rag.ensure_index.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_rag_index_failure_does_not_raise(monkeypatch) -> None:
    monkeypatch.setenv("TEST_MODE", "0")
    monkeypatch.setattr(
        startup_mod, "ApiSessionLocal", lambda: (_ for _ in ()).throw(RuntimeError("db"))
    )
    await startup_mod.ensure_rag_index()  # must not raise


def test_column_migrations_shape() -> None:
    assert "interview_sessions" in cm.SESSIONS_MIGRATIONS
    assert "interview_processes" in cm.SESSIONS_MIGRATIONS
    for table, stmts in cm.SESSIONS_MIGRATIONS.items():
        assert isinstance(stmts, list) and stmts
        for stmt in stmts:
            assert stmt.startswith(f"ALTER TABLE {table} ADD COLUMN ")
    assert any("plan_status" in s for s in cm.SESSIONS_MIGRATIONS["interview_sessions"])
    assert any("round_plan" in s for s in cm.SESSIONS_MIGRATIONS["interview_processes"])
