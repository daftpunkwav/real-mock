"""Models-CRUD tests for realmock.domains.settings.routes.models.

Covers: base-URL guard, model-option listing, provider/model CRUD,
  task bindings, and HTTP smoke for providers/models/bindings.
Conventions: wiped api_db per test; autouse table creation.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from realmock.asgi import app
from realmock.domains.settings.routes import models as models_routes
from realmock.domains.settings.services import model_registry as reg
from realmock.platform.core.errors import ApiBusinessError
from realmock.platform.core.ratelimit import reset_rate_limit


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


class TestSafeBase:
    def test_empty_ok(self) -> None:
        models_routes._safe_base("", label="Base URL")

    def test_bad_scheme(self) -> None:
        with pytest.raises(ApiBusinessError):
            models_routes._safe_base("ftp://x", label="Base URL")

    def test_no_hostname(self) -> None:
        with pytest.raises(ApiBusinessError):
            models_routes._safe_base("http://", label="Base URL")

    def test_prod_suffix(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "realmock.platform.config.get_settings",
            lambda: SimpleNamespace(is_prod=True),
        )
        with pytest.raises(ApiBusinessError, match="production requires https"):
            models_routes._safe_base("http://example.com", label="Base URL")
        models_routes._safe_base("https://example.com", label="Base URL")


class TestListModelOptions:
    def test_filters_disabled(self) -> None:
        p = SimpleNamespace(name="pp")
        on = SimpleNamespace(id=1, provider_id=1, model="a", display_name="", context_window=1, max_output=1, cap_chat=True, cap_vision=False, cap_audio_in=False, cap_audio_out=False, cap_reasoning=False, extras="{}", enabled=True)
        off = SimpleNamespace(id=2, provider_id=1, model="b", display_name="", context_window=1, max_output=1, cap_chat=True, cap_vision=False, cap_audio_in=False, cap_audio_out=False, cap_reasoning=False, extras="{}", enabled=False)
        db = MagicMock()
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr("realmock.domains.settings.routes.models.get_provider_model_rows", lambda db: [(on, p), (off, p)])
            out = models_routes.list_model_options(db)
        assert len(out["models"]) == 1
        assert out["models"][0]["model"] == "a"


class TestProviderCrud:
    def test_create_empty_name(self, api_db) -> None:
        _wipe(api_db)
        with pytest.raises(ApiBusinessError):
            models_routes.create_provider(reg.ProviderCreate(name="   "), api_db)

    def test_create_duplicate(self, api_db) -> None:
        _wipe(api_db)
        _provider(api_db, name="dup")
        with pytest.raises(ApiBusinessError, match="already exists"):
            models_routes.create_provider(reg.ProviderCreate(name="dup"), api_db)

    def test_create_bad_base(self, api_db) -> None:
        _wipe(api_db)
        with pytest.raises(ApiBusinessError):
            models_routes.create_provider(reg.ProviderCreate(name="n1", api_base="ftp://x"), api_db)

    def test_create_happy_encrypts_key(self, api_db) -> None:
        _wipe(api_db)
        out = models_routes.create_provider(reg.ProviderCreate(name="np", api_base="http://x/v1", api_key="sk-1"), api_db)
        assert out["name"] == "np"
        from realmock.platform.models import LlmProvider

        row = api_db.query(LlmProvider).filter(LlmProvider.name == "np").first()
        assert row is not None
        assert row.api_key != "sk-1"
        assert row.api_key.startswith("enc:")

    def test_update_branches(self, api_db) -> None:
        _wipe(api_db)
        p1 = _provider(api_db, name="u1")
        p2 = _provider(api_db, name="u2")
        with pytest.raises(ApiBusinessError):
            models_routes.update_provider(p1.id, reg.ProviderUpdate(name="   "), api_db)
        with pytest.raises(ApiBusinessError, match="already exists"):
            models_routes.update_provider(p1.id, reg.ProviderUpdate(name="u2"), api_db)
        out = models_routes.update_provider(
            p1.id,
            reg.ProviderUpdate(name="u1b", api_base="http://y/v1", protocol="openai_chat", enabled=False, api_key="keep"),
            api_db,
        )
        assert out["name"] == "u1b"
        # keep sentinel leaves key untouched
        out2 = models_routes.update_provider(p2.id, reg.ProviderUpdate(api_key=None), api_db)
        assert out2["name"] == "u2"

    def test_delete_with_models_blocked(self, api_db) -> None:
        _wipe(api_db)
        p = _provider(api_db, name="del1")
        _profile(api_db, p.id, model="mm")
        with pytest.raises(ApiBusinessError, match="Delete all model"):
            models_routes.delete_provider(p.id, api_db)

    def test_delete_happy(self, api_db) -> None:
        _wipe(api_db)
        p = _provider(api_db, name="del2")
        out = models_routes.delete_provider(p.id, api_db)
        assert out["deleted"] == p.id

    def test_list_providers_payload(self, api_db) -> None:
        _wipe(api_db)
        p = _provider(api_db, name="lp", api_key="enc:whatever")
        _profile(api_db, p.id, model="mx")
        out = models_routes.list_providers(api_db)
        assert len(out["providers"]) == 1
        assert out["providers"][0]["has_api_key"] is True
        assert len(out["providers"][0]["models"]) == 1


class TestModelCrud:
    def test_create_empty_and_dup(self, api_db) -> None:
        _wipe(api_db)
        p = _provider(api_db, name="mp")
        with pytest.raises(ApiBusinessError):
            models_routes.create_model(p.id, reg.ModelProfileCreate(model="   "), api_db)
        models_routes.create_model(p.id, reg.ModelProfileCreate(model="dupm"), api_db)
        with pytest.raises(ApiBusinessError, match="already exists"):
            models_routes.create_model(p.id, reg.ModelProfileCreate(model="dupm"), api_db)

    def test_create_happy_extras(self, api_db) -> None:
        _wipe(api_db)
        p = _provider(api_db, name="mp2")
        out = models_routes.create_model(
            p.id,
            reg.ModelProfileCreate(model="m-happy", display_name="Nice", extras={"k": "v"}),
            api_db,
        )
        assert out["model"] == "m-happy"
        assert out["label"] == "Nice"

    def test_update_dup_and_fields(self, api_db) -> None:
        _wipe(api_db)
        p = _provider(api_db, name="mp3")
        a = _profile(api_db, p.id, model="a1")
        b = _profile(api_db, p.id, model="b1")
        with pytest.raises(ApiBusinessError, match="already exists"):
            models_routes.update_model(a.id, reg.ModelProfileUpdate(model="b1"), api_db)
        out = models_routes.update_model(
            a.id,
            reg.ModelProfileUpdate(
                model="a2",
                display_name=" D ",
                context_window=7,
                max_output=8,
                capabilities=reg.ModelCapabilitiesIn(chat=True, vision=True, audio_input=True, audio_output=True, reasoning=True),
                extras={"k2": "v2"},
                enabled=False,
            ),
            api_db,
        )
        assert out["model"] == "a2"
        assert out["capabilities"]["vision"] is True
        assert b.id != a.id

    def test_delete_bound_blocked_and_happy(self, api_db) -> None:
        _wipe(api_db)
        p = _provider(api_db, name="mp4")
        m = _profile(api_db, p.id, model="bound", cap_chat=True)
        from realmock.platform.models import TaskBinding

        api_db.add(TaskBinding(task="chat", profile_id=m.id))
        api_db.commit()
        with pytest.raises(ApiBusinessError, match="bound to a task"):
            models_routes.delete_model(m.id, api_db)
        api_db.query(TaskBinding).delete()
        api_db.commit()
        out = models_routes.delete_model(m.id, api_db)
        assert out["deleted"] == m.id


class TestBindings:
    def test_unknown_task(self, api_db) -> None:
        _wipe(api_db)
        with pytest.raises(ApiBusinessError, match="Unknown task"):
            models_routes.update_binding("nope", reg.BindingUpdate(profile_id=1), api_db)

    def test_capability_mismatch(self, api_db) -> None:
        _wipe(api_db)
        p = _provider(api_db, name="bp")
        m = _profile(api_db, p.id, model="chat-only", cap_chat=True, cap_audio_in=False, cap_audio_out=False)
        with pytest.raises(ApiBusinessError, match="capability"):
            models_routes.update_binding("stt", reg.BindingUpdate(profile_id=m.id), api_db)

    def test_create_and_list_bindings(self, api_db) -> None:
        _wipe(api_db)
        p = _provider(api_db, name="bp2")
        m = _profile(api_db, p.id, model="chat2", cap_chat=True)
        out = models_routes.update_binding("chat", reg.BindingUpdate(profile_id=m.id, fallback_handler="h", fallback_mode="mm"), api_db)
        assert out["chat"]["profile"]["model"] == "chat2"
        listed = models_routes.get_bindings(api_db)
        assert listed["chat"]["fallback"]["handler"] == "h"

    def test_update_existing_binding(self, api_db) -> None:
        _wipe(api_db)
        p = _provider(api_db, name="bp3")
        m1 = _profile(api_db, p.id, model="c1", cap_chat=True)
        m2 = _profile(api_db, p.id, model="c2", cap_chat=True)
        models_routes.update_binding("chat", reg.BindingUpdate(profile_id=m1.id), api_db)
        out = models_routes.update_binding("chat", reg.BindingUpdate(profile_id=m2.id), api_db)
        assert out["chat"]["profile"]["model"] == "c2"


def test_settings_models_http_smoke() -> None:
    reset_rate_limit()
    try:
        with TestClient(app) as client:
            r = client.get("/api/v1/settings/providers")
            assert r.status_code == 200
            assert "providers" in r.json()
            r2 = client.get("/api/v1/settings/models")
            assert r2.status_code == 200
            assert "models" in r2.json()
            r3 = client.get("/api/v1/settings/bindings")
            assert r3.status_code == 200
    finally:
        reset_rate_limit()
