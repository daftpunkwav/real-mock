"""Pipeline legacy tests for realmock.platform.services.pipeline.legacy.

Covers: legacy row fetching, stage migration with and without legacy
  data, and per-stage config builders.
Conventions: wiped api_db per test; autouse table creation.
"""

from __future__ import annotations

import pytest

from realmock.platform.services.pipeline import legacy as plegacy


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


class TestLegacyMigration:
    def test_fetch_none(self, api_db) -> None:
        _wipe(api_db)
        assert plegacy.fetch_llm_settings_row(api_db) is None

    def test_migrate_no_legacy(self, api_db) -> None:
        _wipe(api_db)
        out = plegacy.migrate_legacy_to_stages(api_db)
        assert set(out) == {"recognize", "reason", "speak"}

    def test_migrate_with_legacy(self, api_db) -> None:
        _wipe(api_db)
        from realmock.platform.models import LLMSettings

        api_db.add(LLMSettings(id=1, api_base="http://x/v1", api_key="k", model="m", provider="custom"))
        api_db.commit()
        out = plegacy.migrate_legacy_to_stages(api_db)
        assert out["reason"].model == "m"
        # second run: rows already configured -> untouched
        out2 = plegacy.migrate_legacy_to_stages(api_db)
        assert out2["reason"].model == "m"

    def test_reason_recognize_speak_builders(self, api_db) -> None:
        _wipe(api_db)
        from realmock.platform.models import LLMSettings

        row = LLMSettings(id=1, provider="p", api_base="http://b", api_key="k", model="mm")
        assert plegacy._reason_config_from_legacy(row)["stage"] == "reason"
        assert plegacy._recognize_config_from_legacy(row)["stage"] == "recognize"
        assert plegacy._speak_config_from_legacy(row)["stage"] == "speak"
