"""Registry tests for realmock.domains.settings.services.model_registry.

Covers: provider/profile lookup misses, provider-key handling,
  extras merging with secret redaction, and request-model defaults.
Conventions: wiped api_db per test; autouse table creation.
"""

from __future__ import annotations

import pytest

from realmock.domains.settings.services import model_registry as reg
from realmock.platform.core.errors import ApiBusinessError


@pytest.fixture(autouse=True)
def _clean_api_tables(api_engine):
    import realmock.platform.models  # noqa: F401

    from realmock.platform.database import ApiBase

    ApiBase.metadata.create_all(bind=api_engine)
    yield


def _wipe(api_db) -> None:
    from realmock.platform.models import LlmProvider, ModelProfile, TaskBinding

    api_db.query(TaskBinding).delete()
    api_db.query(ModelProfile).delete()
    api_db.query(LlmProvider).delete()
    api_db.commit()


def _provider(api_db, name="p1", **kw):
    from realmock.platform.models import LlmProvider

    row = LlmProvider(name=name, api_base=kw.get("api_base", "http://x/v1"), protocol=kw.get("protocol", "openai_chat"), api_key=kw.get("api_key", ""), enabled=kw.get("enabled", True))
    api_db.add(row)
    api_db.commit()
    api_db.refresh(row)
    return row


def _profile(api_db, provider_id, model="m1", **kw):
    from realmock.platform.models import ModelProfile

    row = ModelProfile(
        provider_id=provider_id,
        model=model,
        display_name=kw.get("display_name", ""),
        context_window=kw.get("context_window", 1000),
        max_output=kw.get("max_output", 100),
        cap_chat=kw.get("cap_chat", True),
        cap_vision=False,
        cap_audio_in=kw.get("cap_audio_in", False),
        cap_audio_out=kw.get("cap_audio_out", False),
        cap_reasoning=False,
        extras=kw.get("extras", "{}"),
        enabled=kw.get("enabled", True),
    )
    api_db.add(row)
    api_db.commit()
    api_db.refresh(row)
    return row


class TestRegistryLookup:
    def test_get_provider_missing(self, api_db) -> None:
        _wipe(api_db)
        with pytest.raises(ApiBusinessError):
            reg.get_provider(api_db, 999999)

    def test_get_profile_missing(self, api_db) -> None:
        _wipe(api_db)
        with pytest.raises(ApiBusinessError):
            reg.get_profile(api_db, 999999)


class TestRegistryHelpers:
    def test_apply_provider_key_variants(self, api_db) -> None:
        _wipe(api_db)
        p = _provider(api_db, name="kk", api_key="orig")
        reg.apply_provider_key(p, None)
        assert p.api_key == "orig"
        reg.apply_provider_key(p, "keep")
        assert p.api_key == "orig"
        reg.apply_provider_key(p, "")
        assert p.api_key == ""
        reg.apply_provider_key(p, "new-key")
        assert p.api_key.startswith("enc:")

    def test_merge_extras_none(self, api_db) -> None:
        _wipe(api_db)
        p = _provider(api_db, name="ex1")
        m = _profile(api_db, p.id, extras='{"a": 1}')
        assert reg.merge_profile_extras(m, None) == '{"a": 1}'
        m2 = _profile(api_db, p.id, model="ex-none", extras="")
        assert reg.merge_profile_extras(m2, None) == "{}"

    def test_merge_extras_secret_keep_and_encrypt(self, api_db) -> None:
        _wipe(api_db)
        p = _provider(api_db, name="ex2")
        m = _profile(api_db, p.id, model="exs", extras="{}")
        merged = reg.merge_profile_extras(m, {"asr_api_secret": "keep", "plain": "x"})
        import json as _json

        assert _json.loads(merged)["plain"] == "x"
        merged2 = reg.merge_profile_extras(m, {"asr_api_secret": "s3cr3t"})
        assert _json.loads(merged2)["asr_api_secret"].startswith("enc:")

    def test_request_model_defaults(self) -> None:
        assert reg.ProviderCreate(name="x").enabled is True
        assert reg.ModelProfileCreate(model="m").capabilities.chat is True
        assert reg.BindingUpdate(profile_id=1).fallback_handler == ""
