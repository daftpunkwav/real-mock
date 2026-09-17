"""Full-URL channel tests: CRUD round-trip + settings connectivity tests through vendor adapters.

Covers: channel create/update with the full_url flag and payload round-trip,
test_recognize routing to the MiniMax STT adapter for full-URL endpoints,
test_speak routing to the MiniMax TTS adapter, and unknown-endpoint fallback.
Conventions: wiped api_db per test; adapters/HTTP faked (no network).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from realmock.asgi import app
from realmock.domains.settings.services import stage_tests
import realmock.platform.capabilities.voice.stt.router as router_mod
import realmock.platform.capabilities.voice.tts as tts_pkg
from realmock.platform.core.ratelimit import reset_rate_limit


@pytest.fixture(autouse=True)
def _clean_api_tables(api_engine):
    import realmock.platform.models  # noqa: F401

    from realmock.platform.database import ApiBase

    ApiBase.metadata.create_all(bind=api_engine)
    yield


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()


def _wipe(api_db) -> None:
    from realmock.platform.models import LlmProvider, LlmProviderChannel, ModelProfile, TaskBinding

    api_db.query(TaskBinding).delete()
    api_db.query(ModelProfile).delete()
    api_db.query(LlmProviderChannel).delete()
    api_db.query(LlmProvider).delete()
    api_db.commit()


def _mk_provider_profile(api_db, *, api_base: str, model: str, cap: str) -> int:
    from realmock.platform.models import LlmProvider, LlmProviderChannel, ModelProfile

    kind = "stt" if cap == "in" else "tts"
    provider = LlmProvider(name=f"p-{model}")
    api_db.add(provider)
    api_db.flush()
    api_db.add(
        LlmProviderChannel(
            provider_id=provider.id,
            kind=kind,
            api_base=api_base,
            full_url=True,
            protocol="openai_chat",
        )
    )
    profile = ModelProfile(
        provider_id=provider.id,
        kind=kind,
        model=model,
        cap_chat=False,
        cap_audio_in=cap == "in",
        cap_audio_out=cap == "out",
        enabled=True,
    )
    api_db.add(profile)
    api_db.commit()
    api_db.refresh(profile)
    return profile.id


class TestProviderCrudFullUrl:
    def test_create_and_list_round_trip(self, api_db):
        _wipe(api_db)
        client = TestClient(app)
        res = client.post(
            "/api/v1/settings/providers",
            json={
                "name": "ASR 专线",
                "channels": [
                    {"kind": "stt", "api_base": "https://api.minimaxi.com/v1/speech_to_text", "full_url": True}
                ],
            },
        )
        assert res.status_code == 200, res.text
        listed = client.get("/api/v1/settings/providers").json()["providers"]
        row = next(p for p in listed if p["name"] == "ASR 专线")
        channel = next(c for c in row["channels"] if c["kind"] == "stt")
        assert channel["full_url"] is True
        assert channel["api_base"] == "https://api.minimaxi.com/v1/speech_to_text"

    def test_update_flips_flag(self, api_db):
        _wipe(api_db)
        client = TestClient(app)
        pid = client.post("/api/v1/settings/providers", json={"name": "p1"}).json()["id"]
        # Listing backfills a blank chat channel for the bare provider.
        channels = client.get("/api/v1/settings/providers").json()["providers"][0]["channels"]
        assert [(c["kind"], c["full_url"]) for c in channels] == [("chat", False)]
        res = client.put(f"/api/v1/settings/providers/{pid}/channels/stt", json={"full_url": True})
        assert res.status_code == 200, res.text
        channels = client.get("/api/v1/settings/providers").json()["providers"][0]["channels"]
        by_kind = {c["kind"]: c for c in channels}
        assert by_kind["stt"]["full_url"] is True
        assert by_kind["chat"]["full_url"] is False


class TestRecognizeFullUrl:
    @pytest.mark.asyncio
    async def test_routes_to_minimax_adapter(self, api_db, monkeypatch):
        _wipe(api_db)
        profile_id = _mk_provider_profile(
            api_db,
            api_base="https://api.minimaxi.com/v1/speech_to_text",
            model="asr-1.0",
            cap="in",
        )
        _, expected = stage_tests.load_fixture()
        adapter = type(
            "_Adapter",
            (),
            {"transcribe": AsyncMock(return_value=f"前置 {expected} 后置")},
        )()
        monkeypatch.setattr(router_mod, "MiniMaxSttProvider", lambda: adapter)
        result = await stage_tests.test_recognize(api_db, profile_id=profile_id)
        assert result["success"] is True, result
        assert expected in result["transcript"]
        assert result["model"] == "asr-1.0"
        assert "fallback" not in result

    @pytest.mark.asyncio
    async def test_unknown_full_url_endpoint_falls_back(self, api_db, monkeypatch):
        _wipe(api_db)
        profile_id = _mk_provider_profile(
            api_db, api_base="https://vendor.example/whatever", model="asr-1.0", cap="in"
        )
        monkeypatch.setitem(
            router_mod._PROVIDERS, "local", type("_L", (), {"transcribe": AsyncMock(return_value="本地结果")})()
        )
        result = await stage_tests.test_recognize(api_db, profile_id=profile_id)
        assert result["success"] is False
        assert result["fallback"] == "local"
        assert result["transcript"] == "本地结果"


class TestSpeakFullUrl:
    @pytest.mark.asyncio
    async def test_routes_to_minimax_adapter(self, api_db, monkeypatch):
        _wipe(api_db)
        profile_id = _mk_provider_profile(
            api_db,
            api_base="https://api.minimaxi.com/v1/t2a_v2",
            model="speech-2.8-hd",
            cap="out",
        )
        monkeypatch.setattr(
            tts_pkg, "synthesize_minimax_to_base64", AsyncMock(return_value="QUFB")
        )
        result = await stage_tests.test_speak(api_db, profile_id=profile_id)
        assert result["success"] is True, result
        assert result["audio_base64"] == "QUFB"
        assert result["model"] == "speech-2.8-hd"
