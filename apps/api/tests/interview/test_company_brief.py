"""Company brief tests for src/realmock/domains/interview/agents/research/company_brief.py.

Covers: cache key normalization + scope fields, cache round-trip vs generation,
unusable output, cache clearing, singleflight dedup, failure cooldown, cache-write
degradation. Conventions: no real network/LLM (faked); sessions db per test.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from realmock.domains.interview.models import CompanyBrief
from realmock.domains.interview.agents.research import company_brief as cb
from tests.fakes import FakeLLMClient


@pytest.fixture(autouse=True)
def _reset_failure_state():
    """Failure cooldowns are module-global; keep tests isolated from each other."""
    cb._recent_failures.clear()
    yield
    cb._recent_failures.clear()


def _brief_payload() -> dict:
    return {
        "style": "High-frequency probing with quantified follow-ups",
        "focus_areas": ["System design", "Algorithms"],
        "process": "3 rounds: 2 technical + 1 HR",
    }


def test_company_cache_key_normalizes() -> None:
    assert cb.company_cache_key("  ByteDance ", "zh-CN") == cb.company_cache_key("bytedance", "zh-CN")
    # Empty locale falls back to "en".
    assert cb.company_cache_key("acme", "") == cb.company_cache_key("acme", "en")
    assert cb.company_cache_key("acme", "en") != cb.company_cache_key("acme", "zh-CN")


def test_company_cache_key_scopes_by_role_level_type() -> None:
    base = dict(lang="zh-CN")
    assert cb.company_cache_key("acme", "zh-CN") == cb.company_cache_key("acme", "zh-CN")
    assert cb.company_cache_key("acme", **base, role="Backend") != cb.company_cache_key("acme", **base)
    assert cb.company_cache_key("acme", **base, role="Backend", level="mid") != cb.company_cache_key(
        "acme", **base, role="Backend"
    )
    assert cb.company_cache_key(
        "acme", **base, role="Backend", level="mid", interview_type="tech_1"
    ) != cb.company_cache_key("acme", **base, role="Backend", level="mid", interview_type="hr_1")
    # Scope fields normalize the same way the company name does.
    assert cb.company_cache_key("acme", **base, role=" Backend ") == cb.company_cache_key(
        "acme", **base, role="backend"
    )


def test_cache_roundtrip(db) -> None:
    cb.clear_company_briefs(db)
    key = cb.company_cache_key("acme", "zh-CN", role="r", level="l", interview_type="tech_1")
    assert cb.get_cached_brief(
        db, "acme", "zh-CN", role="r", level="l", interview_type="tech_1"
    ) is None
    db.add(
        CompanyBrief(
            company_key=key,
            company_name="acme",
            lang="zh-CN",
            style="s",
            focus_areas=json.dumps(["a"]),
            process="p",
        )
    )
    db.commit()

    out = asyncio.run(
        cb.get_or_create_brief(
            db, None, company="ACME", role="r", level="l", interview_type="tech_1", locale="zh-CN"
        )
    )
    assert out is not None
    assert out["cached"] is True
    assert out["style"] == "s"
    assert out["focus_areas"] == ["a"]


def test_different_interview_type_misses_cache(db) -> None:
    cb.clear_company_briefs(db)
    llm = FakeLLMClient(tokens=[json.dumps(_brief_payload(), ensure_ascii=False)])
    first = asyncio.run(
        cb.get_or_create_brief(
            db, llm, company="Acme", role="Backend", level="mid", interview_type="tech_1", locale="en"
        )
    )
    assert first is not None and first["cached"] is False

    # A different interview type must regenerate instead of reusing tech_1's brief.
    second_llm = FakeLLMClient(tokens=[json.dumps(_brief_payload(), ensure_ascii=False)])
    second = asyncio.run(
        cb.get_or_create_brief(
            db, second_llm, company="Acme", role="Backend", level="mid", interview_type="hr_1", locale="en"
        )
    )
    assert second is not None and second["cached"] is False
    assert len(second_llm.stream_calls) == 1

    # Same combination again hits the cache.
    third_llm = FakeLLMClient(tokens=["must not be consumed"])
    third = asyncio.run(
        cb.get_or_create_brief(
            db, third_llm, company="acme", role="Backend", level="mid", interview_type="tech_1", locale="en"
        )
    )
    assert third is not None and third["cached"] is True
    assert third_llm.stream_calls == []


def test_generate_persists_then_hits_cache(db) -> None:
    cb.clear_company_briefs(db)
    llm = FakeLLMClient(tokens=[json.dumps(_brief_payload(), ensure_ascii=False)])
    out = asyncio.run(
        cb.get_or_create_brief(db, llm, company="Acme", role="Backend", level="mid", locale="zh-CN")
    )
    assert out is not None
    assert out["cached"] is False
    assert out["focus_areas"] == ["System design", "Algorithms"]
    assert cb.get_cached_brief(db, "acme", "zh-CN", role="Backend", level="mid") is not None

    second = FakeLLMClient(tokens=["must not be consumed"])
    again = asyncio.run(
        cb.get_or_create_brief(db, second, company="acme", role="Backend", level="mid", locale="zh-CN")
    )
    assert again is not None and again["cached"] is True
    assert second.stream_calls == []


def test_generate_unusable_output_returns_none(db) -> None:
    cb.clear_company_briefs(db)
    llm = FakeLLMClient(tokens=["I could not find anything."])
    out = asyncio.run(
        cb.get_or_create_brief(db, llm, company="Acme", role="r", level="l", locale="en")
    )
    assert out is None
    assert cb.get_cached_brief(db, "acme", "en") is None


def test_concurrent_requests_share_one_generation(db) -> None:
    cb.clear_company_briefs(db)
    llm = FakeLLMClient(tokens=[json.dumps(_brief_payload(), ensure_ascii=False)])

    async def ask() -> dict | None:
        return await cb.get_or_create_brief(
            db, llm, company="Acme", role="Backend", level="mid", interview_type="tech_1", locale="en"
        )

    async def main() -> tuple[dict | None, dict | None]:
        return await asyncio.gather(ask(), ask())

    first, second = asyncio.run(main())
    assert first is not None and second is not None
    assert {first["cached"], second["cached"]} == {False, True}
    assert len(llm.stream_calls) == 1


def test_failure_cooldown_fails_fast_then_expires(db, monkeypatch) -> None:
    cb.clear_company_briefs(db)
    failing = FakeLLMClient(tokens=["I could not find anything."])
    assert (
        asyncio.run(
            cb.get_or_create_brief(
                db, failing, company="Acme", role="r", level="l", interview_type="tech_1", locale="en"
            )
        )
        is None
    )

    # Inside the cooldown the key fails fast: a new LLM client is never touched.
    retry = FakeLLMClient(tokens=["must not be consumed"])
    assert (
        asyncio.run(
            cb.get_or_create_brief(
                db, retry, company="Acme", role="r", level="l", interview_type="tech_1", locale="en"
            )
        )
        is None
    )
    assert retry.stream_calls == []

    # A different key (other interview type) is not blocked by the cooldown.
    other = FakeLLMClient(tokens=[json.dumps(_brief_payload(), ensure_ascii=False)])
    out = asyncio.run(
        cb.get_or_create_brief(
            db, other, company="Acme", role="r", level="l", interview_type="hr_1", locale="en"
        )
    )
    assert out is not None and out["cached"] is False

    # After the cooldown the failed key may regenerate.
    monkeypatch.setattr(cb, "FAILURE_COOLDOWN_SECONDS", 0.0)
    fresh = FakeLLMClient(tokens=[json.dumps(_brief_payload(), ensure_ascii=False)])
    out = asyncio.run(
        cb.get_or_create_brief(
            db, fresh, company="Acme", role="r", level="l", interview_type="tech_1", locale="en"
        )
    )
    assert out is not None and out["cached"] is False


def test_cache_write_failure_still_returns_brief(db, monkeypatch) -> None:
    cb.clear_company_briefs(db)
    llm = FakeLLMClient(tokens=[json.dumps(_brief_payload(), ensure_ascii=False)])

    def boom() -> None:
        raise RuntimeError("disk full")

    monkeypatch.setattr(db, "commit", boom)
    out = asyncio.run(
        cb.get_or_create_brief(db, llm, company="Acme", role="Backend", level="mid", locale="en")
    )
    assert out is not None
    assert out["cached"] is False
    assert out["style"]
    # The row never landed, so the next request regenerates instead of erroring.
    monkeypatch.undo()
    again = FakeLLMClient(tokens=[json.dumps(_brief_payload(), ensure_ascii=False)])
    second = asyncio.run(
        cb.get_or_create_brief(db, again, company="Acme", role="Backend", level="mid", locale="en")
    )
    assert second is not None and second["cached"] is False


def test_clear_company_briefs(db) -> None:
    cb.clear_company_briefs(db)  # rows from earlier tests may linger
    for name in ("a", "b"):
        db.add(
            CompanyBrief(
                company_key=f"{name}:en",
                company_name=name,
                lang="en",
                style="s",
                focus_areas="[]",
                process="p",
            )
        )
    db.commit()
    assert cb.clear_company_briefs(db) == 2
    assert cb.clear_company_briefs(db) == 0


def test_clear_company_briefs_resets_failure_cooldown(db) -> None:
    cb.clear_company_briefs(db)
    failing = FakeLLMClient(tokens=["I could not find anything."])
    assert (
        asyncio.run(
            cb.get_or_create_brief(
                db, failing, company="Acme", role="r", level="l", interview_type="tech_1", locale="en"
            )
        )
        is None
    )

    # The settings-page clear promises regeneration on the next request, so the
    # in-memory cooldown must die together with the cached rows.
    cb.clear_company_briefs(db)
    fresh = FakeLLMClient(tokens=[json.dumps(_brief_payload(), ensure_ascii=False)])
    out = asyncio.run(
        cb.get_or_create_brief(
            db, fresh, company="Acme", role="r", level="l", interview_type="tech_1", locale="en"
        )
    )
    assert out is not None and out["cached"] is False
