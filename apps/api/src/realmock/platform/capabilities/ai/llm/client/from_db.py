"""LLMClient assembly: from_db / from_stage_config (capability-declared task bindings + legacy-config compatibility).

``from_db`` uses the model-profile system: the scenario's default chat binding, with an explicit
``profile_id`` override; when credentials are missing and the scenario explicitly names a profile,
do not silently fall back (retain profile information so the request reports the error).
At runtime, resolve through the single ``get_stage_config_for_runtime`` path; only environment
variables serve as the final fallback.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from realmock.platform.config import get_settings
from realmock.platform.capabilities.ai.llm.defaults import (
    resolve_context_window,
    resolve_max_output_tokens,
)
from realmock.platform.core.constants import DEFAULT_LLM_PROTOCOL
from realmock.platform.core.secrets import LegacySecretFormatError, decrypt_secret

logger = logging.getLogger(__name__)


def _extras_body_headers(cfg: dict[str, Any]) -> tuple[dict | None, dict | None]:
    """Vendor-specific request customization from model-entry extras (extra_body / extra_headers)."""
    extras = cfg.get("extras") or {}
    if not isinstance(extras, dict):
        return None, None
    extra_body = extras.get("extra_body")
    extra_headers = extras.get("extra_headers")
    return (
        extra_body if isinstance(extra_body, dict) else None,
        extra_headers if isinstance(extra_headers, dict) else None,
    )


def build_from_db(
    cls: type,
    db: Session,
    *,
    profile_id: int | None = None,
    reasoning_effort: str | None = None,
) -> Any:
    """Build a client from the model-profile system (default task binding or scenario-level ``profile_id`` override).

    ``reasoning_effort`` applies only when the selected profile declares ``reasoning_capable``;
    without an override, use the default chat binding, then let the pipeline fall back to stage_configs;
    environment variables are the last-resort fallback.
    """
    from realmock.platform.services.pipeline.config import get_stage_config_for_runtime

    settings = get_settings()
    cfg = get_stage_config_for_runtime(db, "reason", profile_id=profile_id)
    cfg_api_key = cfg.get("api_key") or ""
    profile_explicit = profile_id is not None and cfg.get("profile_id") == profile_id

    if cfg.get("api_base") and cfg_api_key:
        api_base = cfg["api_base"]
        api_key = cfg_api_key
        model = cfg.get("model") or ""
        max_tokens = resolve_max_output_tokens(
            cfg.get("max_tokens") or settings.llm_max_tokens
        )
        protocol = cfg.get("protocol") or DEFAULT_LLM_PROTOCOL
        reasoning = (
            reasoning_effort
            if reasoning_effort and cfg.get("reasoning_capable")
            else None
        )
        extra_body, extra_headers = _extras_body_headers(cfg)
    else:
        if profile_explicit:
            # Entries explicitly specified by the scenario lack credentials: do not fall back silently, retain the entry information and let the request report an error
            return cls(
                api_base=cfg.get("api_base") or "",
                api_key="",
                model=cfg.get("model") or "",
                max_tokens=resolve_max_output_tokens(
                    cfg.get("max_tokens") or settings.llm_max_tokens
                ),
                protocol=cfg.get("protocol") or DEFAULT_LLM_PROTOCOL,
                context_window=resolve_context_window(cfg.get("context_window")),
                supports_vision=bool(cfg.get("supports_vision")),
                full_url=bool(cfg.get("full_url")),
            )
        # The pipeline already contains the stage_configs fallback; here only the environment variables are added to the final level.
        api_base = cfg.get("api_base") or settings.llm_api_base
        raw_api_key = cfg_api_key or settings.llm_api_key
        try:
            api_key = decrypt_secret(raw_api_key) or ""
        except LegacySecretFormatError as e:
            logger.error("API Key uses the old encryption format, please save again: %s", e)
            api_key = ""
        except ValueError as e:
            logger.error("API Key decryption failed: %s", e)
            api_key = ""
        model = cfg.get("model") or settings.llm_model
        max_tokens = resolve_max_output_tokens(
            cfg.get("max_tokens") or settings.llm_max_tokens
        )
        protocol = cfg.get("protocol") or DEFAULT_LLM_PROTOCOL
        reasoning = None
        extra_body, extra_headers = _extras_body_headers(cfg)

    return cls(
        api_base=api_base,
        api_key=api_key,
        model=model,
        max_tokens=max_tokens,
        protocol=protocol or DEFAULT_LLM_PROTOCOL,
        reasoning_effort=reasoning,
        context_window=resolve_context_window(cfg.get("context_window")),
        supports_vision=bool(cfg.get("supports_vision")),
        full_url=bool(cfg.get("full_url")),
        extra_body=extra_body,
        extra_headers=extra_headers,
    )


def build_from_stage_config(cls: type, config: dict[str, Any]) -> Any:
    """Build the client from stage config (stage_tests for connectivity testing)."""
    api_key = config.get("api_key") or ""
    if api_key.startswith("enc:"):
        try:
            api_key = decrypt_secret(api_key) or ""
        except LegacySecretFormatError as e:
            logger.error("API Key uses the old encryption format, please save again: %s", e)
            api_key = ""
        except ValueError as e:
            logger.error("API Key decryption failed: %s", e)
            api_key = ""
    extra_body, extra_headers = _extras_body_headers(config)
    return cls(
        api_base=config.get("api_base") or "",
        api_key=api_key,
        model=config.get("model") or "",
        protocol=config.get("protocol") or DEFAULT_LLM_PROTOCOL,
        max_tokens=resolve_max_output_tokens(config.get("max_tokens")),
        context_window=resolve_context_window(config.get("context_window")),
        supports_vision=bool(config.get("supports_vision")),
        full_url=bool(config.get("full_url")),
        extra_body=extra_body,
        extra_headers=extra_headers,
    )


__all__ = ["build_from_db", "build_from_stage_config"]
