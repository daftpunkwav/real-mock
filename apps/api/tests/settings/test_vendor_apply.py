"""Vendor apply + channel model catalog tests.

Covers: one-click recommended-vendor provisioning (provider + channels + default entries,
idempotent reuse) and the model catalog source selection (vendor descriptor vs remote
OpenAI-compatible /models vs error).
Conventions: wiped api_db per test; HTTP faked (no network).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from realmock.domains.settings.services import vendor_apply as va
from realmock.platform.core.errors import ApiBusinessError


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


class TestApplyVendor:
    def test_unknown_vendor_rejected(self, api_db) -> None:
        _wipe(api_db)
        with pytest.raises(ApiBusinessError, match="Unknown recommended vendor"):
            va.apply_vendor(api_db, "not-a-vendor")

    def test_minimax_provisions_three_channels(self, api_db) -> None:
        _wipe(api_db)
        out = va.apply_vendor(api_db, "minimax")
        from realmock.platform.models import LlmProviderChannel, ModelProfile

        assert out["created_provider"] is True
        assert out["name"] == "MiniMax"
        channels = {
            c.kind: c for c in api_db.query(LlmProviderChannel).filter(LlmProviderChannel.provider_id == out["provider_id"]).all()
        }
        assert set(channels) == {"chat", "stt", "tts"}
        assert channels["chat"].vendor == "minimax"
        assert channels["chat"].api_base  # prefilled from the vendor catalog
        assert channels["chat"].api_key == ""  # key left for the user
        # One default entry per kind, with the kind's capability stamped.
        entries = api_db.query(ModelProfile).filter(ModelProfile.provider_id == out["provider_id"]).all()
        by_kind = {e.kind: e for e in entries}
        assert set(by_kind) == {"chat", "stt", "tts"}
        assert by_kind["chat"].cap_chat is True
        assert by_kind["stt"].cap_audio_in is True
        assert by_kind["tts"].cap_audio_out is True

    def test_reuses_provider_and_never_overwrites(self, api_db) -> None:
        _wipe(api_db)
        first = va.apply_vendor(api_db, "minimax")
        from realmock.platform.models import LlmProviderChannel

        channel = (
            api_db.query(LlmProviderChannel)
            .filter(LlmProviderChannel.provider_id == first["provider_id"], LlmProviderChannel.kind == "chat")
            .first()
        )
        channel.api_base = "https://user-edited.example/v1"
        api_db.commit()
        second = va.apply_vendor(api_db, "minimax")
        assert second["created_provider"] is False
        assert second["provider_id"] == first["provider_id"]
        api_db.refresh(channel)
        assert channel.api_base == "https://user-edited.example/v1"


class TestChannelModelCatalog:
    def _channel(self, api_db, kind, *, vendor="", api_base="", protocol="openai_chat", full_url=False):
        from realmock.platform.models import LlmProvider, LlmProviderChannel

        p = LlmProvider(name="cp")
        api_db.add(p)
        api_db.flush()
        api_db.add(
            LlmProviderChannel(provider_id=p.id, kind=kind, vendor=vendor, api_base=api_base, protocol=protocol, full_url=full_url)
        )
        api_db.commit()
        return p.id

    def test_vendor_descriptor_models(self, api_db) -> None:
        _wipe(api_db)
        pid = self._channel(api_db, "chat", vendor="minimax")
        out = va.channel_model_catalog(api_db, pid, "chat")
        assert out["source"] == "vendor"
        assert "MiniMax-M3" in out["models"]

    def test_remote_openai_models(self, api_db) -> None:
        _wipe(api_db)
        pid = self._channel(api_db, "chat", api_base="https://api.example.com/v1")
        response = type("_R", (), {"raise_for_status": lambda self: None, "json": lambda self: {"data": [{"id": "b-model"}, {"id": "a-model"}]}})()
        with patch.object(va.httpx, "get", return_value=response) as mock_get:
            out = va.channel_model_catalog(api_db, pid, "chat")
        assert out == {"source": "remote", "models": ["a-model", "b-model"]}
        assert mock_get.call_args.args[0] == "https://api.example.com/v1/models"

    def test_remote_failure_raises(self, api_db) -> None:
        _wipe(api_db)
        pid = self._channel(api_db, "chat", api_base="https://api.example.com/v1")
        with patch.object(va.httpx, "get", side_effect=OSError("boom")):
            with pytest.raises(ApiBusinessError, match="Failed to fetch the model list"):
                va.channel_model_catalog(api_db, pid, "chat")

    def test_no_source_raises(self, api_db) -> None:
        _wipe(api_db)
        pid = self._channel(api_db, "stt")  # no vendor, no api_base
        with pytest.raises(ApiBusinessError, match="No model catalog source"):
            va.channel_model_catalog(api_db, pid, "stt")

    def test_unknown_kind_rejected(self, api_db) -> None:
        _wipe(api_db)
        with pytest.raises(ApiBusinessError, match="Unknown channel kind"):
            va.channel_model_catalog(api_db, 1, "voice")
