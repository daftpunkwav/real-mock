"""Pipeline migration tests for realmock.platform.services.pipeline.migration.

Covers: provider-name allocation, stage-data detection, stages-to-profiles migration
  branches, and the legacy flat-provider → per-kind channel backfill (including
  split-provider merging).
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
    from realmock.platform.models import LLMSettings, LlmProvider, LlmProviderChannel, ModelProfile, StageConfig, TaskBinding

    for m in (TaskBinding, ModelProfile, LlmProviderChannel, LlmProvider, StageConfig, LLMSettings):
        api_db.query(m).delete()
    api_db.commit()


class TestAllocateAndMigrateProfiles:
    def test_allocate_suffix(self, api_db) -> None:
        _wipe(api_db)
        from realmock.platform.models import LlmProvider

        api_db.add(LlmProvider(name="dup"))
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

        p = LlmProvider(name="px")
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
        from realmock.platform.models import LlmProviderChannel, TaskBinding

        assert api_db.query(TaskBinding).filter(TaskBinding.task == "chat").first() is not None
        channel = api_db.query(LlmProviderChannel).filter(LlmProviderChannel.kind == "chat").first()
        assert channel is not None
        assert channel.api_base == "http://x/v1"
        assert channel.api_key == "k"


class TestEnsureProviderChannels:
    def _provider(self, api_db, name, **kw):
        from realmock.platform.models import LlmProvider

        row = LlmProvider(name=name, **kw)
        api_db.add(row)
        api_db.flush()
        return row

    def _legacy_flat(self, api_db, provider_id, *, api_base, protocol="openai_chat", api_key="", full_url=False):
        """Add the pre-channel flat columns to the (fresh) table, then fill them for one row.

        Mirrors a real upgraded database, where llm_providers still carries those columns.
        """
        from sqlalchemy import text

        for stmt in (
            "ALTER TABLE llm_providers ADD COLUMN api_base VARCHAR(500) DEFAULT ''",
            "ALTER TABLE llm_providers ADD COLUMN protocol VARCHAR(50) DEFAULT 'openai_chat'",
            "ALTER TABLE llm_providers ADD COLUMN api_key VARCHAR(500) DEFAULT ''",
            "ALTER TABLE llm_providers ADD COLUMN full_url BOOLEAN DEFAULT 0",
        ):
            try:
                api_db.execute(text(stmt))
            except Exception:
                pass  # column already added by an earlier call in the same test
        api_db.execute(
            text(
                "UPDATE llm_providers SET api_base = :b, protocol = :p, api_key = :k, full_url = :f"
                " WHERE id = :id"
            ),
            {"b": api_base, "p": protocol, "k": api_key, "f": int(full_url), "id": provider_id},
        )
        api_db.commit()

    def test_split_rows_merge_into_base(self, api_db) -> None:
        _wipe(api_db)
        from realmock.platform.models import LlmProviderChannel, ModelProfile

        base = self._provider(api_db, "MiniMax")
        self._legacy_flat(api_db, base.id, api_base="https://api.minimaxi.com/v1", api_key="enc:chatkey")
        stt = self._provider(api_db, "MiniMax--语音识别")
        self._legacy_flat(api_db, stt.id, api_base="https://api.minimaxi.com/v1", api_key="enc:sttkey")
        tts = self._provider(api_db, "MiniMax--语音播报")
        self._legacy_flat(api_db, tts.id, api_base="https://api.minimaxi.com/v1")
        api_db.add(ModelProfile(provider_id=base.id, model="MiniMax-M3", cap_chat=True))
        api_db.add(ModelProfile(provider_id=stt.id, model="asr-1.0", cap_audio_in=True))
        api_db.add(ModelProfile(provider_id=tts.id, model="speech-2.8-hd", cap_audio_out=True))
        api_db.commit()

        assert pmig.ensure_provider_channels(api_db) is True

        providers = {p.name: p for p in api_db.query(type(base)).all()}
        assert set(providers) == {"MiniMax"}
        channels = {
            c.kind: c
            for c in api_db.query(LlmProviderChannel).filter(LlmProviderChannel.provider_id == base.id).all()
        }
        assert set(channels) == {"chat", "stt", "tts"}
        assert channels["chat"].api_key == "enc:chatkey"
        assert channels["stt"].api_key == "enc:sttkey"
        assert channels["stt"].vendor == "minimax"
        models = {
            m.model: m for m in api_db.query(ModelProfile).filter(ModelProfile.provider_id == base.id).all()
        }
        assert set(models) == {"MiniMax-M3", "asr-1.0", "speech-2.8-hd"}
        assert models["asr-1.0"].kind == "stt"
        assert models["speech-2.8-hd"].kind == "tts"
        assert models["MiniMax-M3"].kind == "chat"
        # Idempotent: second run is a no-op.
        assert pmig.ensure_provider_channels(api_db) is False

    def test_plain_provider_keeps_flat_columns_on_inferred_kind(self, api_db) -> None:
        _wipe(api_db)
        from realmock.platform.models import LlmProviderChannel, ModelProfile

        p = self._provider(api_db, "MyASR")
        self._legacy_flat(api_db, p.id, api_base="https://asr.example.com", api_key="k1")
        api_db.add(ModelProfile(provider_id=p.id, model="asr-only", cap_audio_in=True))
        api_db.commit()

        assert pmig.ensure_provider_channels(api_db) is True
        channels = api_db.query(LlmProviderChannel).filter(LlmProviderChannel.provider_id == p.id).all()
        assert len(channels) == 1
        assert channels[0].kind == "stt"
        assert channels[0].api_base == "https://asr.example.com"
        profile = api_db.query(ModelProfile).filter(ModelProfile.provider_id == p.id).first()
        assert profile.kind == "stt"

    def test_twin_model_repoints_bindings(self, api_db) -> None:
        _wipe(api_db)
        from realmock.platform.models import ModelProfile, TaskBinding

        base = self._provider(api_db, "MiniMax")
        stt = self._provider(api_db, "MiniMax--语音识别")
        api_db.add(ModelProfile(provider_id=base.id, model="asr-1.0", cap_audio_in=True))
        twin = ModelProfile(provider_id=stt.id, model="asr-1.0", cap_audio_in=True)
        api_db.add(twin)
        api_db.flush()
        binding = TaskBinding(task="stt", profile_id=twin.id)
        api_db.add(binding)
        api_db.commit()

        assert pmig.ensure_provider_channels(api_db) is True
        kept = api_db.query(ModelProfile).filter(ModelProfile.model == "asr-1.0").all()
        assert len(kept) == 1
        api_db.refresh(binding)
        assert binding.profile_id == kept[0].id

    def test_empty_db_noop(self, api_db) -> None:
        _wipe(api_db)
        assert pmig.ensure_provider_channels(api_db) is False

    def test_legacy_columns_dropped_after_backfill(self, api_db) -> None:
        """Upgraded DBs: flat columns are backfilled into channels, then physically
        dropped so ORM inserts no longer hit their NOT NULL constraints."""
        from sqlalchemy import inspect

        _wipe(api_db)
        from realmock.platform.models import LlmProvider

        p = self._provider(api_db, "LegacyP")
        self._legacy_flat(api_db, p.id, api_base="http://old/v1", api_key="k9")
        assert pmig.ensure_provider_channels(api_db) is True
        dropped = pmig.drop_legacy_provider_columns(api_db)
        assert set(dropped) == set(pmig._LEGACY_FLAT_COLUMNS)
        cols = {c["name"] for c in inspect(api_db.bind).get_columns("llm_providers")}
        assert not (cols & set(pmig._LEGACY_FLAT_COLUMNS))
        # ORM insert on the rebuilt table no longer violates legacy constraints.
        api_db.add(LlmProvider(name="FreshP"))
        api_db.commit()
        assert api_db.query(LlmProvider).filter(LlmProvider.name == "FreshP").first() is not None
        # Idempotent: second drop is a no-op.
        assert pmig.drop_legacy_provider_columns(api_db) == []
