"""Isolation, migration, and protocol contract tests for the three-stage BYOK configuration."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from realmock.platform.database import ApiBase
from realmock.platform.models import LLMSettings, StageConfig
from realmock.platform.schemas import StageConfigUpdate
from realmock.platform.capabilities.ai.llm.unified_client import UnifiedLLMClient
from realmock.platform.services.pipeline.config import (
    get_stage_config_for_runtime,
    stage_to_response,
    update_stage_config,
)


def _db():
    engine = create_engine("sqlite:///:memory:")
    ApiBase.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _stage(stage: str, *, base: str, key: str, model: str) -> StageConfigUpdate:
    return StageConfigUpdate(
        provider="custom supplier",
        api_base=base,
        api_key=key,
        protocol="openai_chat",
        model=model,
        max_tokens=1024,
        context_window=8192,
        capabilities={
            "supports_audio_input": stage == "recognize",
            "supports_audio_output": stage != "recognize",
        },
        fallback={
            "handler": "local" if stage == "recognize" else "edge",
            "mode": "transcribe" if stage == "recognize" else "tts_from_text",
        },
    )


def test_stage_configs_are_independent_and_secrets_are_hidden() -> None:
    db = _db()
    try:
        update_stage_config(
            db,
            "recognize",
            _stage(
                "recognize",
                base="https://asr.example.com/v1",
                key="asr-secret",
                model="asr-model",
            ),
        )
        update_stage_config(
            db,
            "reason",
            _stage(
                "reason",
                base="https://llm.example.com/v1",
                key="reason-secret",
                model="reason-model",
            ),
        )

        recognize = get_stage_config_for_runtime(db, "recognize")
        reason = get_stage_config_for_runtime(db, "reason")
        assert recognize["api_key"] == "asr-secret"
        assert reason["api_key"] == "reason-secret"
        assert recognize["model"] != reason["model"]

        public = stage_to_response(
            db.query(StageConfig).filter(StageConfig.stage == "recognize").one()
        )
        assert public["has_api_key"] is True
        assert "api_key" not in public
        assert "asr-secret" not in str(public)
    finally:
        db.close()


def test_default_audio_capabilities_follow_pipeline_stage() -> None:
    db = _db()
    try:
        recognize = get_stage_config_for_runtime(db, "recognize")
        reason = get_stage_config_for_runtime(db, "reason")
        assert recognize["supports_audio_input"] is True
        assert reason["supports_audio_output"] is True
    finally:
        db.close()


def test_legacy_extra_secrets_keep_empty_updates_and_stay_private() -> None:
    db = _db()
    try:
        data = _stage(
            "recognize",
            base="https://asr.example.com/v1",
            key="asr-secret",
            model="asr-model",
        )
        data.extras = {"asr_api_secret": "secret-value", "asr_access_key": "access-value"}
        update_stage_config(db, "recognize", data)

        keep = _stage(
            "recognize",
            base="https://asr.example.com/v1",
            key="keep",
            model="asr-model",
        )
        keep.extras = {"asr_api_secret": "", "asr_access_key": ""}
        update_stage_config(db, "recognize", keep)

        runtime = get_stage_config_for_runtime(db, "recognize")
        public = stage_to_response(
            db.query(StageConfig).filter(StageConfig.stage == "recognize").one()
        )
        assert runtime["extras"]["asr_api_secret"] == "secret-value"
        assert runtime["extras"]["asr_access_key"] == "access-value"
        assert "secret-value" not in str(public)
        assert "access-value" not in str(public)
    finally:
        db.close()


def test_legacy_migration_does_not_overwrite_config_without_provider_name() -> None:
    db = _db()
    try:
        db.add(
            LLMSettings(
                id=1,
                api_base="https://legacy.example.com/v1",
                api_key="legacy-secret",
                model="legacy-model",
                context_window=111,
            )
        )
        db.add_all(
            [
                StageConfig(stage="recognize"),
                StageConfig(
                    stage="reason",
                    provider="",
                    api_base="https://stage.example.com/v1",
                    api_key="stage-secret",
                    model="stage-model",
                    context_window=222,
                ),
                StageConfig(stage="speak"),
            ]
        )
        db.commit()

        config = get_stage_config_for_runtime(db, "reason")
        assert config["api_base"] == "https://stage.example.com/v1"
        assert config["model"] == "stage-model"
        assert config["context_window"] == 222
        assert get_stage_config_for_runtime(db, "recognize")["provider"] == "local"
        assert get_stage_config_for_runtime(db, "speak")["provider"] == "edge"
    finally:
        db.close()


def test_protocol_payloads_include_responses_output_limit_and_tool_shapes() -> None:
    responses = UnifiedLLMClient(
        "https://api.example.com/v1", "key", "model", "openai_responses", 123
    )
    _, response_payload = responses._build_url_and_payload(
        [{"role": "user", "content": "hello"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "parameters": {"type": "object"},
                },
            }
        ],
    )
    assert response_payload["max_output_tokens"] == 123
    assert response_payload["tools"][0]["name"] == "lookup"

    anthropic = UnifiedLLMClient(
        "https://api.example.com/anthropic", "key", "model", "anthropic_messages", 123
    )
    _, anthropic_payload = anthropic._build_url_and_payload(
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "function": {"name": "lookup", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call-1", "content": "done"},
        ],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "parameters": {"type": "object"},
                },
            }
        ],
    )
    assert anthropic_payload["messages"][0]["content"][0]["type"] == "tool_use"
    assert anthropic_payload["messages"][1]["content"][0]["type"] == "tool_result"


def test_anthropic_payload_converts_openai_image_blocks() -> None:
    """OpenAI-style image_url blocks must be converted to Anthropic image blocks, or the gateway returns 400."""
    client = UnifiedLLMClient(
        "https://api.example.com/anthropic", "key", "model", "anthropic_messages", 123
    )
    _, payload = client._build_url_and_payload(
        [
            {"role": "user", "content": "Plain text remains unchanged"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe the image"},
                    {
                        "type": "image_url",
                        "image_url": {"url": "data:image/png;base64,QUJD"},
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": "https://img.example.com/a.jpg"},
                    },
                ],
            },
        ]
    )
    first, second = payload["messages"]
    assert first["content"] == "Plain text remains unchanged"
    blocks = second["content"]
    assert blocks[0] == {"type": "text", "text": "Describe the image"}
    assert blocks[1] == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": "QUJD"},
    }
    assert blocks[2] == {
        "type": "image",
        "source": {"type": "url", "url": "https://img.example.com/a.jpg"},
    }


def test_non_reasoning_provider_ids_derived_from_catalog() -> None:
    """Derive the reason blacklist from the directory: include voice-only IDs and exclude reasoning-capable IDs."""
    from realmock.platform.capabilities.voice.config.catalog import (
        REASONING_PROVIDERS,
        non_reasoning_provider_ids,
    )

    ids = non_reasoning_provider_ids()
    # Voice/transcription-only providers must be selected
    for expected in ("openai_compat", "xfyun", "volcengine", "aliyun", "tencent", "baidu", "local", "edge", "minimax_speech", "none", "mimo_audio"):
        assert expected in ids, expected
    # Exclude IDs declared as reasoning-capable in the reasoning directory (custom / mimo, etc.).
    for p in REASONING_PROVIDERS:
        if p.get("can_interview_reason"):
            assert p["id"] not in ids, p["id"]


def test_legacy_stage_config_defaults_on_empty_db() -> None:
    """Empty-database fallback parsing: max_tokens/context_window on the in-memory default instance must fall back to default values (not None).

    A column default applies only on INSERT; the in-memory instance completed by load_stage_configs
    is not persisted, so _legacy_stage_config must provide its own fallback.
    """
    from realmock.platform.capabilities.ai.llm.defaults import (
        DEFAULT_CONTEXT_WINDOW,
        DEFAULT_MAX_OUTPUT_TOKENS,
    )
    from realmock.platform.models.config_models import StageConfig
    from realmock.platform.services.pipeline.resolve import _legacy_stage_config

    db = _db()
    cfg = _legacy_stage_config(db, "reason")
    assert cfg["max_tokens"] == DEFAULT_MAX_OUTPUT_TOKENS
    assert cfg["context_window"] == DEFAULT_CONTEXT_WINDOW
    assert cfg["protocol"] == "openai_chat"
    # No database write side effects (read-path semantics)
    assert db.query(StageConfig).count() == 0
