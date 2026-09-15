"""Session overrides tests for src/realmock/domains/interview/agents/session_overrides.py.

Covers: parse_ai_overrides, session_llm/STT/TTS credential passthrough
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from realmock.domains.interview.agents.session_overrides import (
    parse_ai_overrides,
    session_llm,
    session_stt_credentials,
    session_tts_credentials,
)
from realmock.domains.interview.agents.session_state import (
    InterviewSessionState,
)
from realmock.domains.interview.models import InterviewSession
from realmock.platform.core.ratelimit import reset_rate_limit


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()


def _llm() -> MagicMock:
    m = MagicMock()
    m.api_key = ""
    return m


def _row(**overrides) -> InterviewSession:
    base = {
        "profile_id": 1,
        "role": "Backend",
        "level": "junior",
        "company": "acme",
        "workflow_type": "technical",
        "status": "pending",
        "current_phase": "identity_check",
        "agent_state": "{}",
        "messages": "[]",
    }
    base.update(overrides)
    return InterviewSession(**base)


def _state(db, **overrides) -> InterviewSessionState:
    row = _row(**overrides)
    db.add(row)
    db.commit()
    db.refresh(row)
    return InterviewSessionState(row, _llm())


# ---- _is_summary_phase ----




# ---- load / clamp ----












# ---- notes ----












# ---- pace ----










# ---- phase queries ----








# ---- progression ----










# ---- session_overrides ----


def test_parse_ai_overrides_variants() -> None:
    assert parse_ai_overrides(SimpleNamespace(ai_overrides="")) == {}
    assert parse_ai_overrides(SimpleNamespace(ai_overrides="{bad")) == {}
    assert parse_ai_overrides(SimpleNamespace(ai_overrides="[1]")) == {}
    assert parse_ai_overrides(SimpleNamespace(ai_overrides='{"a":1}')) == {"a": 1}
    assert parse_ai_overrides(SimpleNamespace()) == {}


def test_session_llm_honors_overrides() -> None:
    from realmock.platform.capabilities.ai.llm.client import LLMClient

    sess = SimpleNamespace(
        ai_overrides=json.dumps({"chat_profile_id": 3, "reasoning_effort": "high"})
    )
    with patch.object(LLMClient, "from_db", return_value=MagicMock()) as m:
        session_llm(MagicMock(), sess)
        _, kwargs = m.call_args
        assert kwargs.get("profile_id") == 3


def test_session_stt_tts_credentials_passthrough() -> None:
    sess = SimpleNamespace(ai_overrides=json.dumps({"stt_profile_id": 2, "tts_profile_id": 4}))
    with (
        patch(
            "realmock.platform.services.pipeline.config.get_stage_config_for_runtime",
            return_value=MagicMock(),
        ) as cfg,
        patch(
            "realmock.platform.capabilities.voice.config.credentials.build_stt_credentials",
            return_value=MagicMock(),
        ) as stt,
        patch(
            "realmock.platform.capabilities.voice.config.credentials.build_tts_credentials",
            return_value=MagicMock(),
        ) as tts,
    ):
        session_stt_credentials(MagicMock(), sess)
        session_tts_credentials(MagicMock(), sess)
        assert cfg.call_count == 2
        stt.assert_called_once()
        tts.assert_called_once()


# ---- compaction thresholds ----














# ---- round plan schema extras ----








# ---- round planner background ----












