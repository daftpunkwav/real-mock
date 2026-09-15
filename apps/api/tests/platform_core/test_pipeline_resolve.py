"""Pipeline resolve tests for realmock.platform.services.pipeline.resolve.

Covers: profile response shaping, provider/model row loading, runtime
  config decryption, binding selection, and legacy fallbacks.
Conventions: wiped api_db per test; autouse table creation.
"""

from __future__ import annotations

import json

import pytest

from realmock.platform.services.pipeline import resolve as pres


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


class TestResolve:
    def _mk(self, api_db):
        _wipe(api_db)
        from realmock.platform.models import LlmProvider, ModelProfile

        p = LlmProvider(name="rp", api_base="http://p/v1", protocol="openai_chat", api_key="plain-key")
        api_db.add(p)
        api_db.flush()
        m = ModelProfile(provider_id=p.id, model="mm", display_name="", context_window=0, max_output=0, cap_chat=True, cap_vision=True, cap_audio_in=False, cap_audio_out=False, cap_reasoning=True, extras="{}", enabled=True)
        api_db.add(m)
        api_db.commit()
        api_db.refresh(m)
        return p, m

    def test_profile_to_response_no_provider(self, api_db) -> None:
        _wipe(api_db)
        from realmock.platform.models import ModelProfile

        m = ModelProfile(provider_id=1, model="m", display_name="", context_window=1, max_output=1)
        out = pres.profile_to_response(m, None)
        assert out["provider_name"] == ""
        assert out["label"] == "m"

    def test_profile_to_response_redacts(self, api_db) -> None:
        p, m = self._mk(api_db)
        m.extras = json.dumps({"asr_api_secret": "x", "ok": 1})
        out = pres.profile_to_response(m, p)
        assert "asr_api_secret" not in out["extras"]
        assert out["extras"]["ok"] == 1

    def test_get_provider_model_rows(self, api_db) -> None:
        p, m = self._mk(api_db)
        rows = pres.get_provider_model_rows(api_db)
        assert len(rows) == 1
        assert rows[0][1].name == "rp"

    def test_runtime_from_profile_plain_and_enc(self, api_db) -> None:
        from realmock.platform.core.secrets import encrypt_secret

        p, m = self._mk(api_db)
        out = pres._runtime_config_from_profile(m, p, "reason")
        assert out["api_key"] == "plain-key"
        assert out["reasoning_capable"] is True
        p.api_key = encrypt_secret("hidden")
        api_db.commit()
        out2 = pres._runtime_config_from_profile(m, p, "reason")
        assert out2["api_key"] == "hidden"
        p.api_key = "enc:v2:bad:bad:bad:bad"
        api_db.commit()
        with pytest.raises(ValueError, match="decryption failed"):
            pres._runtime_config_from_profile(m, p, "reason")
        # no provider branch
        out3 = pres._runtime_config_from_profile(m, None, "reason")
        assert out3["api_key"] == ""

    def test_binding_config_branches(self, api_db) -> None:
        _wipe(api_db)
        assert pres._binding_config(api_db, "chat", "reason") is None
        p, m = self._mk(api_db)
        from realmock.platform.models import TaskBinding

        api_db.add(TaskBinding(task="chat", profile_id=999999))
        api_db.commit()
        assert pres._binding_config(api_db, "chat", "reason") is None
        api_db.query(TaskBinding).delete()
        api_db.add(TaskBinding(task="chat", profile_id=m.id, fallback_handler="h", fallback_mode="mm"))
        api_db.commit()
        out = pres._binding_config(api_db, "chat", "reason")
        assert out["model"] == "mm"

    def test_legacy_stage_config_empty(self, api_db) -> None:
        _wipe(api_db)
        out = pres._legacy_stage_config(api_db, "reason")
        assert "provider" in out
        assert out["reasoning_capable"] is False
