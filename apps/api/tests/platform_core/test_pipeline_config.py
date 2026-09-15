"""Pipeline config tests for realmock.platform.services.pipeline.config.

Covers: stage updates with secret handling, legacy-aware config maps,
  profile/binding resolution precedence, and migration aliases.
Conventions: wiped api_db per test; autouse table creation.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from realmock.platform.services.pipeline import config as pconf


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


class TestPipelineConfig:
    def _data(self, **kw):
        base = {
            "provider": "custom",
            "api_base": "http://x/v1",
            "api_key": "k",
            "protocol": "openai_chat",
            "model": "m",
            "max_tokens": 10,
            "context_window": 100,
            "capabilities": SimpleNamespace(supports_vision=True, supports_audio_input=True, supports_audio_output=True, supports_video_input=False),
            "fallback": SimpleNamespace(handler="h", mode="mm"),
            "extras": {"plain": "v", "asr_api_secret": "s"},
        }
        base.update(kw)
        return SimpleNamespace(**base)

    def test_update_stage_config_full(self, api_db) -> None:
        _wipe(api_db)
        row = pconf.update_stage_config(api_db, "reason", self._data())
        assert row.provider == "custom"
        extras = json.loads(row.extras)
        assert extras["source"] == "stage"
        assert extras["asr_api_secret"].startswith("enc:")
        # keep sentinel preserves secret
        row2 = pconf.update_stage_config(api_db, "reason", self._data(extras={"asr_api_secret": "keep"}, capabilities=None, fallback=None))
        assert json.loads(row2.extras)["asr_api_secret"].startswith("enc:")

    def test_get_stage_config_map_with_legacy(self, api_db) -> None:
        _wipe(api_db)
        from realmock.platform.models import LLMSettings

        api_db.add(LLMSettings(id=1, api_base="http://leg/v1", api_key="k", model="leg-m"))
        api_db.commit()
        out = pconf.get_stage_config_map(api_db)
        assert set(out) == {"recognize", "reason", "speak"}

    def test_resolve_model_config_profile_override(self, api_db) -> None:
        _wipe(api_db)
        from realmock.platform.models import LlmProvider, ModelProfile

        p = LlmProvider(name="ov", api_base="http://o/v1", protocol="openai_chat")
        api_db.add(p)
        api_db.flush()
        m = ModelProfile(provider_id=p.id, model="over", cap_chat=True)
        api_db.add(m)
        api_db.commit()
        out = pconf.resolve_model_config(api_db, "reason", profile_id=m.id)
        assert out["model"] == "over"
        # missing profile id falls through to binding/legacy
        out2 = pconf.resolve_model_config(api_db, "reason", profile_id=999999)
        assert "model" in out2

    def test_resolve_prefers_binding(self, api_db) -> None:
        _wipe(api_db)
        from realmock.platform.models import LlmProvider, ModelProfile, TaskBinding

        p = LlmProvider(name="bnd", api_base="http://b/v1", protocol="openai_chat")
        api_db.add(p)
        api_db.flush()
        m = ModelProfile(provider_id=p.id, model="bound-m", cap_chat=True)
        api_db.add(m)
        api_db.flush()
        api_db.add(TaskBinding(task="chat", profile_id=m.id))
        api_db.commit()
        out = pconf.resolve_model_config(api_db, "reason")
        assert out["model"] == "bound-m"
        assert pconf.get_stage_config_for_runtime(api_db, "reason")["model"] == "bound-m"

    def test_ensure_pipeline_migrated(self, api_db) -> None:
        _wipe(api_db)
        pconf.ensure_pipeline_migrated(api_db)
        # alias exists
        assert pconf.get_stage_config_for_runtime_v2 is pconf.get_stage_config_for_runtime
