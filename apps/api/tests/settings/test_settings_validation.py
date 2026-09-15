"""Validation tests for realmock.domains.settings.services.validation.

Covers: base-URL safety and per-stage provider validation branches.
Conventions: settings and provider catalog stubbed; no network.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from realmock.domains.settings.services.validation import safe_base, validate_stage_config
from realmock.platform.core.errors import ApiBusinessError
from realmock.platform.schemas import StageConfigUpdate


class TestSafeBase:
    def test_empty_passes(self) -> None:
        safe_base("", label="Base URL")
        safe_base("   ", label="Base URL")

    def test_valid_http_passes(self) -> None:
        safe_base("http://localhost:8081/v1", label="Base URL")

    def test_invalid_raises(self) -> None:
        with pytest.raises(ApiBusinessError) as e:
            safe_base("not-a-url", label="Base URL")
        assert e.value.status_code == 400
        with pytest.raises(ApiBusinessError):
            safe_base("ftp://x/y", label="Base URL")

    def test_prod_requires_https(self, monkeypatch) -> None:
        monkeypatch.setattr("realmock.domains.settings.services.validation.get_settings", lambda: SimpleNamespace(is_prod=True))
        with pytest.raises(ApiBusinessError, match="production requires https"):
            safe_base("http://example.com/v1", label="Base URL")
        safe_base("https://example.com/v1", label="Base URL")

    def test_nonprod_allows_http(self, monkeypatch) -> None:
        monkeypatch.setattr("realmock.domains.settings.services.validation.get_settings", lambda: SimpleNamespace(is_prod=False))
        safe_base("http://example.com/v1", label="Base URL")


class TestValidateStageConfig:
    def _update(self, provider: str) -> StageConfigUpdate:
        return StageConfigUpdate(provider=provider)

    def test_recognize_coming_soon_raises(self) -> None:
        with pytest.raises(ApiBusinessError) as e:
            validate_stage_config("recognize", self._update("zhipu_glm4_voice"))
        assert e.value.status_code == 400

    def test_recognize_normal_passes(self) -> None:
        validate_stage_config("recognize", self._update("local"))

    def test_reason_blacklist_raises(self) -> None:
        with pytest.raises(ApiBusinessError) as e:
            validate_stage_config("reason", self._update("local"))
        assert "text LLM" in e.value.detail

    def test_reason_capable_passes(self) -> None:
        validate_stage_config("reason", self._update("custom"))

    def test_reason_incapable_meta_raises(self, monkeypatch) -> None:
        import realmock.domains.settings.services.validation as v

        monkeypatch.setattr(v, "non_reasoning_provider_ids", lambda: frozenset())
        monkeypatch.setattr(v, "find_provider", lambda stage, pid: {"can_interview_reason": False, "status": "active"})
        with pytest.raises(ApiBusinessError):
            validate_stage_config("reason", self._update("whatever"))

    def test_reason_coming_soon_meta_passes(self, monkeypatch) -> None:
        import realmock.domains.settings.services.validation as v

        monkeypatch.setattr(v, "non_reasoning_provider_ids", lambda: frozenset())
        monkeypatch.setattr(v, "find_provider", lambda stage, pid: {"can_interview_reason": False, "status": "coming_soon"})
        validate_stage_config("reason", self._update("whatever"))

    def test_speak_coming_soon_raises(self) -> None:
        with pytest.raises(ApiBusinessError):
            validate_stage_config("speak", self._update("doubao_s2s"))

    def test_speak_normal_passes(self) -> None:
        validate_stage_config("speak", self._update("edge"))

    def test_unknown_stage_passes(self) -> None:
        validate_stage_config("other", self._update("x"))
