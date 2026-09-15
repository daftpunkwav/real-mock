"""Pipeline stages tests for realmock.platform.services.pipeline.stages.

Covers: get-or-create with compat backfill, load vs persist-all,
  and response shaping.
Conventions: wiped api_db per test; autouse table creation.
"""

from __future__ import annotations

import pytest

from realmock.platform.services.pipeline import stages as pstages


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


class TestStages:
    def test_get_or_create_and_backfill(self, api_db) -> None:
        _wipe(api_db)
        row = pstages.get_or_create_stage_config(api_db, "recognize")
        assert row.stage == "recognize"
        assert row.fallback_handler == "local"
        # second call hits existing branch; force empty provider to trigger compat backfill
        row.provider = ""
        row.api_base = ""
        row.model = ""
        row.supports_audio_input = False
        row.fallback_handler = ""
        api_db.commit()
        row2 = pstages.get_or_create_stage_config(api_db, "recognize")
        assert row2.supports_audio_input is True
        assert row2.fallback_handler == "local"

    def test_speak_backfill(self, api_db) -> None:
        _wipe(api_db)
        row = pstages.get_or_create_stage_config(api_db, "speak")
        row.provider = ""
        row.api_base = ""
        row.model = ""
        row.fallback_handler = ""
        api_db.commit()
        row2 = pstages.get_or_create_stage_config(api_db, "speak")
        assert row2.fallback_handler == "edge"

    def test_load_vs_get_all(self, api_db) -> None:
        _wipe(api_db)
        loaded = pstages.load_stage_configs(api_db)
        assert set(loaded) == {"recognize", "reason", "speak"}
        # load does not persist
        from realmock.platform.models import StageConfig

        assert api_db.query(StageConfig).count() == 0
        all_rows = pstages.get_all_stage_configs(api_db)
        assert len(all_rows) == 3

    def test_stage_to_response(self, api_db) -> None:
        _wipe(api_db)
        row = pstages.get_or_create_stage_config(api_db, "reason")
        out = pstages.stage_to_response(row)
        assert out["stage"] == "reason"
        assert "capabilities" in out
        assert "has_api_key" in out
