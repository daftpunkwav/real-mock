"""Seed tests for realmock.platform.services.seed.

Covers: no-key short-circuit, existing-key preservation, and fresh writes.
Conventions: wiped api_db per test; settings stubbed via monkeypatch.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _ensure_tables(api_engine):
    import realmock.platform.models  # noqa: F401

    from realmock.platform.database import ApiBase

    ApiBase.metadata.create_all(bind=api_engine)
    yield


def _wipe(api_db) -> None:
    from realmock.platform.models import LLMSettings, LlmProvider, ModelProfile, StageConfig, TaskBinding

    for m in (TaskBinding, ModelProfile, LlmProvider, StageConfig, LLMSettings):
        api_db.query(m).delete()
    api_db.commit()


class TestSeed:
    def test_no_key_returns(self, api_db, monkeypatch) -> None:
        from realmock.platform.services import seed as sd

        _wipe(api_db)
        monkeypatch.setattr(sd, "get_settings", lambda: SimpleNamespace(llm_api_key=""))
        sd.seed_llm_settings(api_db)

    def test_existing_key_returns(self, api_db, monkeypatch) -> None:
        from realmock.platform.services import seed as sd
        from realmock.platform.services.pipeline import stages as pstages

        _wipe(api_db)
        row = pstages.get_or_create_stage_config(api_db, "reason")
        row.api_key = "enc:existing"
        api_db.commit()
        monkeypatch.setattr(
            sd,
            "get_settings",
            lambda: SimpleNamespace(llm_api_key="k", llm_api_base="http://b", llm_model="m", llm_max_tokens=1, llm_context_window=2),
        )
        sd.seed_llm_settings(api_db)
        assert api_db.query(type(row)).filter(type(row).stage == "reason").first().api_key == "enc:existing"

    def test_seed_writes(self, api_db, monkeypatch) -> None:
        from realmock.platform.services import seed as sd

        _wipe(api_db)
        monkeypatch.setattr(
            sd,
            "get_settings",
            lambda: SimpleNamespace(llm_api_key="sk-new", llm_api_base="http://nb/v1", llm_model="nm", llm_max_tokens=11, llm_context_window=22),
        )
        sd.seed_llm_settings(api_db)
        from realmock.platform.models import StageConfig

        row = api_db.query(StageConfig).filter(StageConfig.stage == "reason").first()
        assert row is not None
        assert row.api_key.startswith("enc:")
        assert row.model == "nm"
