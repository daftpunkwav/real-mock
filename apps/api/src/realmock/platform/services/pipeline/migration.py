"""Three ``stage_configs`` rows → provider + model profile + task bindings (one-time import).

``allocate_provider_name`` and ``migrate_stages_to_profiles`` must remain in the same file:
the ``llm_providers.name`` UNIQUE suffix logic is coupled to the import flow, and separating
them would reintroduce the regression.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from realmock.platform.core.constants import DEFAULT_LLM_PROTOCOL, DEFAULT_MAX_OUTPUT_TOKENS, PipelineStage
from realmock.platform.models import LlmProvider, ModelProfile, StageConfig, TaskBinding
from realmock.platform.services.pipeline.stages import STAGES, get_all_stage_configs

# old stage name → neutral task name. The stage vocabulary appears only in paths that are compatible with this mapping and the API.
TASK_BY_STAGE = {
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


def _stage_has_data(row: StageConfig | None) -> bool:
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
                api_base=row.api_base or "",
                protocol=row.protocol or DEFAULT_LLM_PROTOCOL,
                api_key=row.api_key or "",
            )
            db.add(provider)
            db.flush()
            providers_by_key[key] = provider
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
