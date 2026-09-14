"""Profile schema unit tests: tech_domains coercion helpers, required-string strip, and Update model validators.

Pure unit layer — no TestClient, no database. The HTTP behavior built on these
helpers is covered in test_profile_api.py; contract drift alarms live in
test_profile_contract_guard.py.
"""

from __future__ import annotations

import pytest

from realmock.domains.profile.schemas.required import REQUIRED_STRING_FIELDS, strip_nonblank
from realmock.domains.profile.schemas.tech_domains import (
    clean_tech_domains,
    normalize_update_domains,
)
from realmock.domains.profile.schemas.update import UserProfileUpdate


def test_clean_tech_domains_skips_non_strings() -> None:
    assert clean_tech_domains([" Python ", 42, None, "", "Go", "Python", "  "]) == [
        "Python",
        "Go",
    ]
    assert clean_tech_domains([1, 2, 3]) == []


def test_normalize_update_domains_accepts_json_string_or_list() -> None:
    assert normalize_update_domains('[" Python ", "Go", "Go"]') == ["Python", "Go"]
    assert normalize_update_domains([" Go ", "Go", ""]) == ["Go"]


def test_normalize_update_domains_bad_input_falls_back() -> None:
    assert normalize_update_domains("{not-json") == []
    assert normalize_update_domains('{"a": 1}') == []
    # Non-string, non-list values pass through untouched; the Update model rejects them (422).
    assert normalize_update_domains(42) == 42


def test_strip_nonblank_passes_through_non_strings() -> None:
    assert strip_nonblank("  Ada  ") == "Ada"
    assert strip_nonblank(42) == 42
    assert strip_nonblank(None) is None


# --- Update model validators (defense-in-depth branches) ---


def test_update_field_validator_rejects_empty_domain_list() -> None:
    """The explicit field validator fires even if list length constraints ever pass."""
    with pytest.raises(ValueError, match="at least one technical field"):
        UserProfileUpdate._tech_domains_nonempty([])


def test_update_model_validator_reports_missing_required() -> None:
    """The post-construction re-check lists every blank required key plus tech_domains."""
    blank = {name: "" for name in REQUIRED_STRING_FIELDS}
    instance = UserProfileUpdate.model_construct(**blank, tech_domains=[])
    with pytest.raises(ValueError) as exc_info:
        UserProfileUpdate._assert_required_present(instance)
    message = str(exc_info.value)
    assert message.startswith("Missing required fields: ")
    for name in REQUIRED_STRING_FIELDS:
        assert name in message
    assert "tech_domains" in message


def test_update_model_validator_passes_complete_instance() -> None:
    """A fully filled instance survives the re-check unchanged."""
    payload = UserProfileUpdate.model_validate(
        {
            "name": "Test user",
            "identity": "Employed",
            "job_direction": "Backend development",
            "target_role": "Backend engineer",
            "self_intro": "introduce",
            "tech_domains": ["Python"],
        }
    )
    assert UserProfileUpdate._assert_required_present(payload) is payload
