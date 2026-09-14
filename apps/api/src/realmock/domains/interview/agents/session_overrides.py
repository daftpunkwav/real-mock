"""Parse session-level AI overrides (ai_overrides).

An interview session can specify the model entry and reasoning effort separately for three tasks (reasoning chat / speech input stt / speech output tts);
missing fields fall back to task bindings (default handlers).
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from realmock.platform.capabilities.ai.llm.client import LLMClient
    from realmock.platform.capabilities.voice.stt.base import SttCredentials
    from realmock.platform.capabilities.voice.tts import TtsCredentials

logger = logging.getLogger(__name__)


def parse_ai_overrides(session: Any) -> dict[str, Any]:
    """Decode the session's ``ai_overrides`` JSON (per-task profile ids + effort).

    Args:
        session: Interview session row (or duck-typed carrier of ``ai_overrides``).

    Returns:
        Override mapping; ``{}`` when unset, corrupt, or not a JSON object
        (callers then fall back to task bindings).
    """
    try:
        data = json.loads(getattr(session, "ai_overrides", None) or "{}")
    except json.JSONDecodeError:
        logger.debug("corrupt ai_overrides JSON; fall back to task bindings")
        return {}
    return data if isinstance(data, dict) else {}


def session_llm(db: Session, session: Any) -> "LLMClient":
    """Build the reasoning-chat LLM client for a session.

    Args:
        db: API database session for profile/binding lookup.
        session: Interview session row carrying ``ai_overrides``.

    Returns:
        Client honoring ``chat_profile_id`` / ``reasoning_effort`` overrides,
        else the default chat binding.
    """
    from realmock.platform.capabilities.ai.llm.client import LLMClient

    overrides = parse_ai_overrides(session)
    return LLMClient.from_db(
        db,
        profile_id=overrides.get("chat_profile_id"),
        reasoning_effort=overrides.get("reasoning_effort"),
    )


def session_stt_credentials(db: Session, session: Any) -> "SttCredentials":
    """Resolve speech-input credentials for a session.

    Args:
        db: API database session for binding lookup.
        session: Interview session row carrying ``ai_overrides``.

    Returns:
        Credentials honoring the ``stt_profile_id`` override, else the
        default recognize binding (degrading to local transcription).
    """
    from realmock.platform.capabilities.voice.config.credentials import build_stt_credentials
    from realmock.platform.core.constants import PipelineStage
    from realmock.platform.services.pipeline.config import get_stage_config_for_runtime

    cfg = get_stage_config_for_runtime(
        db, PipelineStage.RECOGNIZE, profile_id=parse_ai_overrides(session).get("stt_profile_id")
    )
    return build_stt_credentials(cfg)


def session_tts_credentials(db: Session, session: Any) -> "TtsCredentials":
    """Resolve speech-output credentials for a session.

    Args:
        db: API database session for binding lookup.
        session: Interview session row carrying ``ai_overrides``.

    Returns:
        Credentials honoring the ``tts_profile_id`` override, else the
        default speak binding (degrading to edge synthesis / captions-only).
    """
    from realmock.platform.capabilities.voice.config.credentials import build_tts_credentials
    from realmock.platform.core.constants import PipelineStage
    from realmock.platform.services.pipeline.config import get_stage_config_for_runtime

    cfg = get_stage_config_for_runtime(
        db, PipelineStage.SPEAK, profile_id=parse_ai_overrides(session).get("tts_profile_id")
    )
    return build_tts_credentials(cfg)
