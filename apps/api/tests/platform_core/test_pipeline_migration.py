"""Pipeline migration tests for realmock.platform.services.pipeline.migration.

Covers: provider-name allocation, stage-data detection, and
  stages-to-profiles migration branches.
Conventions: wiped api_db per test; autouse table creation.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from realmock.platform.services.pipeline import migration as pmig


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


class TestAllocateAndMigrateProfiles:
    def test_allocate_suffix(self, api_db) -> None:
        _wipe(api_db)
        from realmock.platform.models import LlmProvider

        api_db.add(LlmProvider(name="dup", api_base="", protocol="openai_chat"))
        api_db.commit()
        assert pmig.allocate_provider_name(api_db, "dup", set()) == "dup (2)"
        assert pmig.allocate_provider_name(api_db, "  ", set()) == "custom supplier"
        assert pmig.allocate_provider_name(api_db, "", set()) != ""

    def test_stage_has_data(self) -> None:
        assert pmig._stage_has_data(None) is False
        assert pmig._stage_has_data(SimpleNamespace(provider="", api_base="", model="", api_key="")) is False
        assert pmig._stage_has_data(SimpleNamespace(provider="x", api_base="", model="", api_key="")) is True

    def test_migrate_noop_when_profiles_exist(self, api_db) -> None:
        _wipe(api_db)
        from realmock.platform.models import LlmProvider, ModelProfile

        p = LlmProvider(name="px", api_base="", protocol="openai_chat")
        api_db.add(p)
        api_db.flush()
        api_db.add(ModelProfile(provider_id=p.id, model="m"))
        api_db.commit()
        assert pmig.migrate_stages_to_profiles(api_db) is False

    def test_migrate_noop_when_no_data(self, api_db) -> None:
        _wipe(api_db)
        assert pmig.migrate_stages_to_profiles(api_db) is False

    def test_migrate_happy(self, api_db) -> None:
        _wipe(api_db)
        from realmock.platform.services.pipeline import stages as pstages

        row = pstages.get_or_create_stage_config(api_db, "reason")
        row.provider = "custom"
        row.api_base = "http://x/v1"
        row.model = "gpt-x"
        row.api_key = "k"
        api_db.commit()
        assert pmig.migrate_stages_to_profiles(api_db) is True
        from realmock.platform.models import TaskBinding

        assert api_db.query(TaskBinding).filter(TaskBinding.task == "chat").first() is not None
