"""Models-CRUD tests for realmock.domains.settings.routes.models.

Covers: base-URL guard, model-option listing, provider/channel/model CRUD,
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
    from realmock.platform.models import LlmProvider, LlmProviderChannel, ModelProfile, TaskBinding

    api_db.query(TaskBinding).delete()
    api_db.query(ModelProfile).delete()
    api_db.query(LlmProviderChannel).delete()
    api_db.query(LlmProvider).delete()
    api_db.commit()


def _provider(api_db, name="p1", *, kind="chat", api_base="http://x/v1", protocol="openai_chat", api_key="", enabled=True):
    """Provider + one channel (defaults to the chat kind)."""
    from realmock.platform.models import LlmProvider, LlmProviderChannel

    row = LlmProvider(name=name, enabled=enabled)
    api_db.add(row)
    api_db.flush()
    channel = LlmProviderChannel(
        provider_id=row.id,
        kind=kind,
        api_base=api_base,
        protocol=protocol,
        api_key=api_key,
    )
    api_db.add(channel)
    api_db.commit()
    api_db.refresh(row)
    return row


def _profile(api_db, provider_id, model="m1", kind="chat", **kw):
    from realmock.platform.models import ModelProfile

    row = ModelProfile(
        provider_id=provider_id,
        kind=kind,
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
        on = SimpleNamespace(id=1, provider_id=1, kind="chat", model="a", display_name="", context_window=1, max_output=1, cap_chat=True, cap_vision=False, cap_audio_in=False, cap_audio_out=False, cap_reasoning=False, extras="{}", enabled=True)
        off = SimpleNamespace(id=2, provider_id=1, kind="chat", model="b", display_name="", context_window=1, max_output=1, cap_chat=True, cap_vision=False, cap_audio_in=False, cap_audio_out=False, cap_reasoning=False, extras="{}", enabled=False)
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
        body = reg.ProviderCreate(
            name="n1",
            channels=[reg.ChannelWrite(kind="chat", api_base="ftp://x")],
        )
        with pytest.raises(ApiBusinessError):
            models_routes.create_provider(body, api_db)

    def test_create_happy_encrypts_key(self, api_db) -> None:
        _wipe(api_db)
        body = reg.ProviderCreate(
            name="np",
            channels=[reg.ChannelWrite(kind="chat", api_base="http://x/v1", api_key="sk-1")],
        )
        out = models_routes.create_provider(body, api_db)
        assert out["name"] == "np"
        from realmock.platform.models import LlmProviderChannel

        channel = api_db.query(LlmProviderChannel).filter(LlmProviderChannel.provider_id == out["id"]).first()
        assert channel is not None
        assert channel.api_key != "sk-1"
        assert channel.api_key.startswith("enc:")

    def test_update_branches(self, api_db) -> None:
        _wipe(api_db)
        p1 = _provider(api_db, name="u1")
        p2 = _provider(api_db, name="u2")
        with pytest.raises(ApiBusinessError):
            models_routes.update_provider(p1.id, reg.ProviderUpdate(name="   "), api_db)
        with pytest.raises(ApiBusinessError, match="already exists"):
            models_routes.update_provider(p1.id, reg.ProviderUpdate(name="u2"), api_db)
        out = models_routes.update_provider(p1.id, reg.ProviderUpdate(name="u1b", enabled=False), api_db)
        assert out["name"] == "u1b"

    def test_website_and_notes_roundtrip(self, api_db) -> None:
        _wipe(api_db)
        body = reg.ProviderCreate(name="meta", website_url="https://example.com", notes="k8s 内网")
        out = models_routes.create_provider(body, api_db)
        with pytest.raises(ApiBusinessError):
            models_routes.update_provider(out["id"], reg.ProviderUpdate(website_url="not a url"), api_db)
        models_routes.update_provider(
            out["id"], reg.ProviderUpdate(website_url="https://x.io", notes="n2"), api_db
        )
        item = next(
            i for i in reg.list_providers_payload(api_db)["providers"] if i["id"] == out["id"]
        )
        assert item["website_url"] == "https://x.io"
        assert item["notes"] == "n2"

    def test_delete_cascades_models_channels_bindings(self, api_db) -> None:
        _wipe(api_db)
        from realmock.platform.models import ModelProfile, TaskBinding

        p = _provider(api_db, name="del1")
        _profile(api_db, p.id, model="mm")
        profile = api_db.query(ModelProfile).filter(ModelProfile.model == "mm").first()
        profile_id = profile.id
        api_db.add(TaskBinding(task="chat", profile_id=profile_id))
        api_db.commit()

        out = models_routes.delete_provider(p.id, api_db)
        assert out["deleted"] == p.id
        assert api_db.query(ModelProfile).filter(ModelProfile.provider_id == p.id).count() == 0
        assert api_db.query(TaskBinding).filter(TaskBinding.profile_id == profile_id).count() == 0
        assert api_db.query(TaskBinding).count() == 0

    def test_delete_happy_removes_channels(self, api_db) -> None:
        _wipe(api_db)
        p = _provider(api_db, name="del2")
        out = models_routes.delete_provider(p.id, api_db)
        assert out["deleted"] == p.id
        from realmock.platform.models import LlmProviderChannel

        assert api_db.query(LlmProviderChannel).filter(LlmProviderChannel.provider_id == p.id).count() == 0

    def test_list_providers_payload(self, api_db) -> None:
        _wipe(api_db)
        p = _provider(api_db, name="lp", api_key="enc:whatever")
        _profile(api_db, p.id, model="mx")
        out = models_routes.list_providers(api_db)
        assert len(out["providers"]) == 1
        provider = out["providers"][0]
        assert provider["channels"][0]["has_api_key"] is True
        assert provider["channels"][0]["kind"] == "chat"
        assert len(provider["models"]) == 1
        assert provider["models"][0]["kind"] == "chat"


class TestChannelUpsert:
    def test_unknown_kind_rejected(self, api_db) -> None:
        _wipe(api_db)
        p = _provider(api_db, name="ck")
        with pytest.raises(ApiBusinessError, match="Unknown channel kind"):
            models_routes.update_provider_channel(p.id, "voice", reg.ChannelUpdate(api_base="http://x"), api_db)

    def test_upsert_creates_then_updates(self, api_db) -> None:
        _wipe(api_db)
        p = _provider(api_db, name="ck2")
        out = models_routes.update_provider_channel(
            p.id, "stt", reg.ChannelUpdate(api_base="http://asr/v1", api_key="sk-stt"), api_db
        )
        assert out["kind"] == "stt"
        assert out["has_api_key"] is True
        # Second call updates in place instead of duplicating.
        out2 = models_routes.update_provider_channel(
            p.id, "stt", reg.ChannelUpdate(api_base="http://asr2/v1"), api_db
        )
        assert out2["api_base"] == "http://asr2/v1"
        from realmock.platform.models import LlmProviderChannel

        rows = api_db.query(LlmProviderChannel).filter(LlmProviderChannel.provider_id == p.id, LlmProviderChannel.kind == "stt").all()
        assert len(rows) == 1


class TestModelCrud:
    def test_create_empty_and_dup(self, api_db) -> None:
        _wipe(api_db)
        p = _provider(api_db, name="mp")
        with pytest.raises(ApiBusinessError):
            models_routes.create_model(p.id, reg.ModelProfileCreate(model="   "), api_db)
        models_routes.create_model(p.id, reg.ModelProfileCreate(model="dupm"), api_db)
        with pytest.raises(ApiBusinessError, match="already exists"):
            models_routes.create_model(p.id, reg.ModelProfileCreate(model="dupm"), api_db)

    def test_create_with_kind(self, api_db) -> None:
        _wipe(api_db)
        p = _provider(api_db, name="mp2")
        out = models_routes.create_model(p.id, reg.ModelProfileCreate(model="asr-x", kind="stt"), api_db)
        assert out["kind"] == "stt"
        with pytest.raises(ApiBusinessError, match="Unknown model type"):
            models_routes.create_model(p.id, reg.ModelProfileCreate(model="bad", kind="voice"), api_db)

    def test_create_happy_extras(self, api_db) -> None:
        _wipe(api_db)
        p = _provider(api_db, name="mp3")
        out = models_routes.create_model(
            p.id,
            reg.ModelProfileCreate(model="m-happy", display_name="Nice", extras={"k": "v"}),
            api_db,
        )
        assert out["model"] == "m-happy"
        assert out["label"] == "Nice"

    def test_update_dup_and_fields(self, api_db) -> None:
        _wipe(api_db)
        p = _provider(api_db, name="mp4")
        a = _profile(api_db, p.id, model="a1")
        b = _profile(api_db, p.id, model="b1")
        with pytest.raises(ApiBusinessError, match="already exists"):
            models_routes.update_model(a.id, reg.ModelProfileUpdate(model="b1"), api_db)
        out = models_routes.update_model(
            a.id,
            reg.ModelProfileUpdate(
                model="a2",
                kind="tts",
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
        assert out["kind"] == "tts"
        assert out["capabilities"]["vision"] is True
        assert b.id != a.id

    def test_delete_bound_blocked_and_happy(self, api_db) -> None:
        _wipe(api_db)
        p = _provider(api_db, name="mp5")
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
