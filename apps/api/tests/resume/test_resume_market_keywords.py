"""Market keywords tests for src/realmock/domains/resume/services/market_keywords.py.

Covers: _parsed_profile bad-JSON branches, _push_token limit/dedup/stopword/
truncation branches, infer_search_keywords target/skills/projects/raw-text
branches, infer_target_role_from_resume fallback branches, infer_resume_query_locale
branches.
Conventions: no real network/model downloads (all clients mocked); pure text logic;
rate limits reset per test.
"""

from __future__ import annotations

import json

import pytest

from realmock.platform.models import Resume


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    from realmock.platform.core.ratelimit import reset_rate_limit

    reset_rate_limit()
    yield
    reset_rate_limit()


def _resume(**over) -> Resume:
    base = {"filename": "resume.pdf", "file_type": "pdf", "raw_text": "", "parsed_profile": "{}"}
    base.update(over)
    return Resume(**base)


def test_parsed_profile_bad_json() -> None:
    from realmock.domains.resume.services import market_keywords as mk

    r = _resume(parsed_profile="{bad json")
    assert mk._parsed_profile(r) == {}
    r2 = _resume(parsed_profile="[1,2]")
    assert mk._parsed_profile(r2) == {}


def test_push_token_limits_and_truncation() -> None:
    from realmock.domains.resume.services import market_keywords as mk

    seen: set[str] = set()
    out: list[str] = []
    mk._push_token(seen, out, "   ", limit=8)
    mk._push_token(seen, out, "Python", limit=8)
    mk._push_token(seen, out, "python", limit=8)  # dup (case-insensitive)
    mk._push_token(seen, out, "the", limit=8)  # stopword
    assert out == ["Python"]
    # Truncation to 48 chars.
    mk._push_token(seen, out, "x" * 60, limit=8)
    assert len(out[1]) == 48
    # Limit reached -> no-op.
    full = ["a", "b"]
    mk._push_token(set(), full, "c", limit=2)
    assert full == ["a", "b"]


def test_infer_keywords_target_role_and_skills() -> None:
    from realmock.domains.resume.services import market_keywords as mk

    profile = {"target_role": "Backend Engineer", "skills": ["Python", "the", "Go"]}
    r = _resume(parsed_profile=json.dumps(profile), filename="weird_name-test.pdf")
    kws = mk.infer_search_keywords(r, limit=8)
    assert "Backend Engineer" in kws
    assert "Python" in kws
    assert "the" not in [k.lower() for k in kws]


def test_infer_keywords_project_stacks() -> None:
    from realmock.domains.resume.services import market_keywords as mk

    profile = {
        "projects": [
            {"name": "ProjA", "tech_stack": "Python, Go/Redis"},
            {"name": "ProjB", "tech_stack": ["K8s", "the"]},
            "not-a-dict",
        ],
        "summary": "Built Python services with Redis",
    }
    r = _resume(parsed_profile=json.dumps(profile), raw_text="ExtraTokenXYZ Golang")
    kws = mk.infer_search_keywords(r, limit=10)
    assert "ProjA" in kws
    assert "Python" in kws
    assert "K8s" in kws


def test_infer_keywords_raw_text_fallback() -> None:
    from realmock.domains.resume.services import market_keywords as mk

    r = _resume(parsed_profile="{}", filename="a.pdf", raw_text="Kubernetes Docker Python")
    kws = mk.infer_search_keywords(r, limit=5)
    assert len(kws) > 0


def test_infer_target_role_fallback_to_keywords() -> None:
    from realmock.domains.resume.services import market_keywords as mk

    r = _resume(parsed_profile=json.dumps({"skills": ["Python", "Redis"]}))
    assert mk.infer_target_role_from_resume(r) != ""
    r2 = _resume(parsed_profile=json.dumps({"desired_role": "Data Analyst"}))
    assert mk.infer_target_role_from_resume(r2) == "Data Analyst"
    r3 = _resume(parsed_profile="{}")
    assert mk.infer_target_role_from_resume(r3) == ""


def test_infer_query_locale_zh_en() -> None:
    from realmock.domains.resume.services import market_keywords as mk

    r = _resume(raw_text="你好，我熟悉Python", filename="a.pdf")
    assert mk.infer_resume_query_locale(r) in ("zh-CN", "en")
