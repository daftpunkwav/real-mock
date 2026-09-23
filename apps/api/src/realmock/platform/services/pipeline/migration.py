"""Three ``stage_configs`` rows → provider + model profile + task bindings (one-time import).

``allocate_provider_name`` / ``migrate_stages_to_profiles`` / ``ensure_provider_channels``
must remain in the same file: the ``llm_providers.name`` UNIQUE suffix logic and the legacy
flat-column backfill are coupled to the import flow, and separating them would reintroduce
the regression.
"""

from __future__ import annotations

import logging
import re
from typing import TypeGuard

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from realmock.platform.core.constants import DEFAULT_LLM_PROTOCOL, DEFAULT_MAX_OUTPUT_TOKENS, PipelineStage
from realmock.platform.models import LlmProvider, LlmProviderChannel, ModelProfile, StageConfig, TaskBinding
from realmock.platform.services.pipeline.stages import STAGES, get_all_stage_configs

logger = logging.getLogger(__name__)

# old stage name → neutral task name. The stage vocabulary appears only in paths that are compatible with this mapping and the API.
TASK_BY_STAGE: dict[str, str] = {
    PipelineStage.REASON: "chat",
    PipelineStage.RECOGNIZE: "stt",
    PipelineStage.SPEAK: "tts",
}
STAGE_BY_TASK = {task: stage for stage, task in TASK_BY_STAGE.items()}
# Default downgrade strategy (same as seed for old get_or_create_stage_config)
DEFAULT_FALLBACK = {
    "chat": {"handler": "", "mode": ""},
    "stt": {"handler": "local", "mode": "transcribe"},
    "tts": {"handler": "edge", "mode": "tts_from_text"},
}


def _stage_has_data(row: StageConfig | None) -> "TypeGuard[StageConfig]":
    return bool(row and (row.provider or row.api_base or row.model or row.api_key))


def allocate_provider_name(db: Session, desired: str, taken: set[str]) -> str:
    """``llm_providers.name`` is unique: append a numeric suffix when entries have the same display name but different api_base values."""
    base = (desired or "custom supplier").strip() or "custom supplier"
    candidate = base
    n = 2
    while candidate in taken or db.query(LlmProvider).filter(LlmProvider.name == candidate).first() is not None:
        candidate = f"{base} ({n})"
        n += 1
    taken.add(candidate)
    return candidate


def migrate_stages_to_profiles(db: Session) -> bool:
    """One-time import: three stage_configs rows → provider + model entry + task binding.

    Run only when the model entry table is empty and at least one stage row contains data; idempotent.
    Return whether an import occurred.
    """
    if db.query(ModelProfile).count() > 0:
        return False
    rows = get_all_stage_configs(db)
    if not any(_stage_has_data(row) for row in rows.values()):
        return False

    providers_by_key: dict[tuple[str, str], LlmProvider] = {}
    taken_names = {p.name for p in db.query(LlmProvider).all()}
    bound: dict[str, int] = {}
    for stage in STAGES:
        row = rows.get(stage)
        if not _stage_has_data(row):
            continue
        task = TASK_BY_STAGE[stage]
        key = ((row.provider or "").lower(), row.api_base or "")
        provider = providers_by_key.get(key)
        if provider is None:
            provider = LlmProvider(
                name=allocate_provider_name(db, row.provider or "custom supplier", taken_names),
            )
            db.add(provider)
            db.flush()
            providers_by_key[key] = provider
        # The stage row carries per-task connection settings; import them as that kind's channel.
        db.add(
            LlmProviderChannel(
                provider_id=provider.id,
                kind=task,
                api_base=row.api_base or "",
                protocol=row.protocol or DEFAULT_LLM_PROTOCOL,
                api_key=row.api_key or "",
            )
        )
        caps = {
            "cap_chat": stage == PipelineStage.REASON,
            "cap_vision": bool(row.supports_vision),
            "cap_audio_in": bool(row.supports_audio_input),
            "cap_audio_out": bool(row.supports_audio_output),
            # There is no thinking intensity statement in the old system; set it to False conservatively, and check it on the settings page if necessary.
            "cap_reasoning": False,
        }
        profile = ModelProfile(
            provider_id=provider.id,
            kind=task,
            model=row.model or "",
            context_window=row.context_window or 0,
            max_output=row.max_tokens or DEFAULT_MAX_OUTPUT_TOKENS,
            extras=row.extras or "{}",
            **caps,
        )
        db.add(profile)
        db.flush()
        bound[task] = profile.id
    for task, profile_id in bound.items():
        db.add(
            TaskBinding(
                task=task,
                profile_id=profile_id,
                fallback_handler=DEFAULT_FALLBACK[task]["handler"],
                fallback_mode=DEFAULT_FALLBACK[task]["mode"],
            )
        )
    db.commit()
    return True


# ── Legacy flat provider columns → per-kind channels ────────────────────────────

# Legacy split-provider naming: "<base><sep><voice suffix>" carried per-type connection
# settings as separate llm_providers rows. The known suffix words are part of the pattern
# so the lazy base backtracks until the tail is one of them; the separator is lenient
# (dashes, underscore, whitespace) because the historical rows were hand-created under
# inconsistent conventions.
_SPLIT_NAME_RE = re.compile(
    r"^(?P<base>.+?)(?P<sep>[-—_\s]+)?(?P<suffix>语音识别|语音播报|语音合成|STT|ASR|TTS)$",
    re.IGNORECASE,
)
_SPLIT_KIND_BY_SUFFIX = {
    "语音识别": "stt",
    "语音播报": "tts",
    "语音合成": "tts",
    "stt": "stt",
    "asr": "stt",
    "tts": "tts",
}
# Latin suffixes need an explicit separator ("MiniMax-stt" merges; "fasttts" is a plain name).
_LATIN_SUFFIXES = frozenset({"stt", "asr", "tts"})

# Flat connection columns that used to live on llm_providers before channels existed.
_LEGACY_FLAT_COLUMNS = ("api_base", "full_url", "protocol", "api_key")


def _split_channel_kind(name: str) -> tuple[str, str] | None:
    """``(base, channel kind)`` when the name is a legacy split-provider row, else None."""
    match = _SPLIT_NAME_RE.match((name or "").strip())
    if not match:
        return None
    suffix = match.group("suffix").lower()
    base = match.group("base").strip()
    kind = _SPLIT_KIND_BY_SUFFIX.get(suffix)
    if not kind or not base:
        return None
    if suffix in _LATIN_SUFFIXES and not match.group("sep"):
        return None
    return base, kind


def _infer_profile_kind(profile: ModelProfile) -> str:
    """Chat-capable entries stay under the chat channel; pure one-direction audio entries
    map to their voice channel."""
    if profile.cap_audio_in and not profile.cap_audio_out and not profile.cap_chat:
        return "stt"
    if profile.cap_audio_out and not profile.cap_audio_in and not profile.cap_chat:
        return "tts"
    return "chat"


def _infer_provider_kind(profiles: list[ModelProfile]) -> str:
    """Channel kind a legacy provider's flat columns describe: its uniform voice kind, else chat."""
    kinds = {_infer_profile_kind(p) for p in profiles}
    if kinds == {"stt"}:
        return "stt"
    if kinds == {"tts"}:
        return "tts"
    return "chat"


def _guess_vendor(name: str) -> str:
    """Catalog vendor id when the provider name names one (e.g. "MiniMax" → "minimax"); else ""."""
    candidate = (name or "").strip().lower()
    if not candidate:
        return ""
    from realmock.platform.capabilities.voice.config.catalog import catalog_payload
    from realmock.platform.vendors import VENDOR_LABELS

    ids = {vendor_id.lower() for vendor_id in VENDOR_LABELS}
    for table in catalog_payload().values():
        for provider in table:
            ids.add(str(provider.get("id") or "").lower())
    return candidate if candidate in ids else ""


def _legacy_flat_columns(db: Session) -> dict[int, dict[str, object]]:
    """Read the pre-channel flat columns straight from llm_providers (missing on fresh DBs).

    The ORM no longer declares these columns, so the backfill goes through raw SQL; only the
    columns physically present are read, so a pre-``full_url`` database still backfills its
    real api_base/protocol/api_key values (missing keys default in :func:`_channel_from_legacy`).
    Returns an empty mapping when none of the columns exist (fresh install).
    """
    inspector = inspect(db.bind)
    if inspector is None:
        return {}
    existing = {column["name"] for column in inspector.get_columns("llm_providers")}
    legacy_cols = [column for column in _LEGACY_FLAT_COLUMNS if column in existing]
    if not legacy_cols:
        return {}
    columns_sql = ", ".join(legacy_cols)
    rows = db.execute(text(f"SELECT id, {columns_sql} FROM llm_providers")).mappings().all()
    return {row["id"]: dict(row) for row in rows}


def _channel_from_legacy(legacy: dict[str, object], provider_id: int, kind: str, vendor: str = "") -> LlmProviderChannel:
    return LlmProviderChannel(
        provider_id=provider_id,
        kind=kind,
        vendor=vendor,
        api_base=str(legacy.get("api_base") or ""),
        full_url=bool(legacy.get("full_url")),
        protocol=str(legacy.get("protocol") or "") or DEFAULT_LLM_PROTOCOL,
        api_key=str(legacy.get("api_key") or ""),
    )


def drop_legacy_provider_columns(db: Session) -> list[str]:
    """Physically remove the pre-channel flat columns from llm_providers (SQLite >= 3.35).

    Must run AFTER :func:`ensure_provider_channels` so legacy values are backfilled into
    channels first. Surviving rows keep a NOT NULL constraint on those columns, which
    breaks ORM inserts that no longer supply them — dropping the columns removes both the
    dead data and the constraint. Idempotent: missing columns are skipped.
    """
    engine = db.bind
    if engine is None:
        return []
    existing = {column["name"] for column in inspect(engine).get_columns("llm_providers")}
    dropped: list[str] = []
    for column in _LEGACY_FLAT_COLUMNS:
        if column in existing:
            db.execute(text(f"ALTER TABLE llm_providers DROP COLUMN {column}"))
            dropped.append(column)
    if dropped:
        db.commit()
        logger.info("Dropped legacy llm_providers columns: %s", ", ".join(dropped))
    return dropped


def ensure_provider_channels(db: Session) -> bool:
    """One-time backfill: legacy flat llm_providers columns → llm_provider_channels rows.

    Pass 1 merges legacy split rows ("<base>--语音识别/语音播报") into their base provider as
    stt/tts channels, moving their model entries along; pass 2 gives every remaining provider
    the channel its flat columns describe (uniform voice kind when all entries are pure voice,
    else chat) and tags each entry with its channel kind. Idempotent: providers that already
    own the target channel are left untouched. Returns whether any backfill happened.
    """
    providers = db.query(LlmProvider).order_by(LlmProvider.id).all()
    if not providers:
        return False
    legacy = _legacy_flat_columns(db)
    changed = False

    # Pass 1: fold split rows into their base provider.
    by_lower: dict[str, LlmProvider] = {}
    for provider in providers:
        by_lower.setdefault(provider.name.lower(), provider)
    for provider in providers:
        split = _split_channel_kind(provider.name)
        if split is None:
            continue
        base_name, kind = split
        target = by_lower.get(base_name.lower())
        if target is None:
            target = LlmProvider(name=base_name, enabled=provider.enabled)
            db.add(target)
            db.flush()
            by_lower[base_name.lower()] = target
        if target.id == provider.id:
            continue
        channel = (
            db.query(LlmProviderChannel)
            .filter(LlmProviderChannel.provider_id == target.id, LlmProviderChannel.kind == kind)
            .first()
        )
        if channel is None:
            db.add(
                _channel_from_legacy(
                    legacy.get(provider.id, {}), target.id, kind, vendor=_guess_vendor(base_name)
                )
            )
        elif not channel.vendor:
            # Untagged channel: adopt the vendor id so deep adapters engage.
            channel.vendor = _guess_vendor(base_name)
        for profile in db.query(ModelProfile).filter(ModelProfile.provider_id == provider.id).all():
            twin = (
                db.query(ModelProfile)
                .filter(
                    ModelProfile.provider_id == target.id,
                    ModelProfile.model == profile.model,
                    ModelProfile.id != profile.id,
                )
                .first()
            )
            if twin is None:
                profile.provider_id = target.id
                profile.kind = kind
            else:
                # Same model already lives under the merged provider: repoint bindings, drop the twin.
                db.query(TaskBinding).filter(TaskBinding.profile_id == profile.id).update(
                    {"profile_id": twin.id}, synchronize_session=False
                )
                db.delete(profile)
        # The split row and any channels still pointing at it are superseded by the target.
        db.query(LlmProviderChannel).filter(LlmProviderChannel.provider_id == provider.id).delete()
        db.delete(provider)
        changed = True
    db.flush()

    # Pass 2: give every surviving provider the channel its flat columns describe.
    for provider in db.query(LlmProvider).order_by(LlmProvider.id).all():
        profiles = (
            db.query(ModelProfile)
            .filter(ModelProfile.provider_id == provider.id)
            .order_by(ModelProfile.id)
            .all()
        )
        kind = _infer_provider_kind(profiles)
        channel = (
            db.query(LlmProviderChannel)
            .filter(LlmProviderChannel.provider_id == provider.id, LlmProviderChannel.kind == kind)
            .first()
        )
        if channel is None:
            db.add(
                _channel_from_legacy(
                    legacy.get(provider.id, {}), provider.id, kind, vendor=_guess_vendor(provider.name)
                )
            )
            changed = True
        for profile in profiles:
            profile.kind = _infer_profile_kind(profile)
    if changed:
        db.commit()
    return changed
