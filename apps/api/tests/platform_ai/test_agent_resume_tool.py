"""Resume tool tests for apps/api/src/realmock/platform/capabilities/ai/agent/tools/resume.py.

Covers: snapshot parsing, contact/link bundles and resume_overview/resume_get_section
handlers (overview, paging, focus filter, error branches).

Conventions: no network, async handlers; asyncio_mode=auto.
"""

from __future__ import annotations

import json

import pytest

from realmock.platform.capabilities.ai.agent.tools import resume as resume_mod
from realmock.platform.capabilities.ai.agent.tools.resume import (
    ResumeSnapshot,
    _contact_bundle,
    _github_urls_from_text,
    resume_tool_specs,
    snapshot_from_payload,
)


def _snap(**kw) -> ResumeSnapshot:
    base = {
        "resume_id": 1,
        "filename": "r.pdf",
        "file_type": "pdf",
        "raw_text": "hello test@example.com 13800138000 https://github.com/owner/repo",
        "parsed": {
            "name": "Ada",
            "target_role": "SWE",
            "education": [{"school": "X"}],
            "work_experience": [{"company": "Y"}],
            "projects": [{"name": "P1"}, "plain", {"other": 1}],
            "skills": ["Python", "Go", ""],
            "summary": "great",
            "city": "Shanghai",
            "email": "",
            "phone": "",
            "github_urls": [],
            "links": ["https://example.com"],
            "languages": ["en"],
            "awards": [],
            "publications": [],
        },
        "layout_notes": "note",
        "has_visual_pages": True,
    }
    base.update(kw)
    return ResumeSnapshot(**base)  # type: ignore[arg-type]


def test_github_urls_dedup_and_git_suffix() -> None:
    urls = _github_urls_from_text(
        "https://github.com/Owner/Repo.git and https://github.com/owner/repo and https://github.com/a/b"
    )
    assert urls[0] == "https://github.com/Owner/Repo"
    assert len(urls) == 2


def test_github_urls_limit() -> None:
    text = " ".join(f"https://github.com/o/r{i}" for i in range(20))
    assert len(_github_urls_from_text(text, limit=8)) == 8
    assert _github_urls_from_text("") == []


def test_snapshot_from_payload_variants() -> None:
    s = snapshot_from_payload(
        {"resume_id": "7", "filename": "a", "file_type": "pdf", "raw_text": "t", "parsed": {"a": 1}},
        has_visual_pages=True,
    )
    assert s.resume_id == 7
    assert s.has_visual_pages is True
    s2 = snapshot_from_payload({"resume_id": 0, "parsed": "bad", "layout_notes": "L"})
    assert s2.parsed == {}
    assert s2.layout_notes == "L"
    s3 = snapshot_from_payload({"parsed": {"layout_notes": "PL"}})
    assert s3.layout_notes == "PL"


def test_as_list_and_project_names() -> None:
    assert resume_mod._as_list("x") == []
    assert resume_mod._as_list([1]) == [1]
    assert resume_mod._project_names({"projects": [{"name": " A "}, "", {"x": 1}]})[0] == "A"
    many = {"projects": [{"name": f"p{i}"} for i in range(30)]}
    assert len(resume_mod._project_names(many)) == resume_mod.RESUME_OVERVIEW_PROJECT_MAX


def test_skill_labels_truncation() -> None:
    skills = [f"s{i}" for i in range(50)]
    out = resume_mod._skill_labels({"skills": skills})
    assert len(out) == resume_mod.RESUME_OVERVIEW_SKILL_MAX
    assert resume_mod._skill_labels({}) == []


def test_contact_bundle_parsed_and_regex() -> None:
    c = _contact_bundle({"email": "a@b.com", "phone": "123", "city": "BJ"}, "x")
    assert c["email"] == "a@b.com"
    c2 = _contact_bundle({}, "mail me at foo@bar.com and 13800138000")
    assert c2["email"] == "foo@bar.com"
    assert "13800138000" in c2["phone"]
    c3 = _contact_bundle({}, "no contact")
    assert c3["email"] == "" and c3["phone"] == ""


def test_link_bundle_prefers_parsed() -> None:
    b = resume_mod._link_bundle({"github_urls": ["https://github.com/x/y"], "links": ["L"]}, "t")
    assert b["github_urls"] == ["https://github.com/x/y"]
    b2 = resume_mod._link_bundle({}, "see https://github.com/o/r")
    assert b2["github_urls"] == ["https://github.com/o/r"]


@pytest.mark.asyncio
async def test_overview_handler() -> None:
    specs = {s.name: s for s in resume_tool_specs(_snap())}
    assert set(specs) == {"resume_overview", "resume_get_section"}
    out = json.loads(await specs["resume_overview"].handler({}))
    assert out["name"] == "Ada"
    assert out["project_names"] == ["P1", "plain"]
    assert "Python" in out["skills"]
    assert out["contact"]["city"] == "Shanghai"
    assert len(out["available_sections"]) == 7


@pytest.mark.asyncio
async def test_overview_degraded_and_empty() -> None:
    snap = _snap(parsed={}, raw_text="", layout_notes="x" * 500)
    specs = {s.name: s for s in resume_tool_specs(snap)}
    out = json.loads(await specs["resume_overview"].handler({}))
    assert out["parse_degraded"] is False
    assert len(out["layout_notes"]) <= 400


@pytest.mark.asyncio
async def test_get_section_unknown() -> None:
    specs = {s.name: s for s in resume_tool_specs(_snap())}
    out = json.loads(await specs["resume_get_section"].handler({"section": "nope"}))
    assert out["error"] == "unknown_section"


@pytest.mark.asyncio
async def test_get_section_education_work() -> None:
    specs = {s.name: s for s in resume_tool_specs(_snap())}
    edu = json.loads(await specs["resume_get_section"].handler({"section": "education"}))
    assert edu["data"][0]["school"] == "X"
    work = json.loads(await specs["resume_get_section"].handler({"section": "work"}))
    assert work["data"][0]["company"] == "Y"


@pytest.mark.asyncio
async def test_get_section_projects_focus() -> None:
    specs = {s.name: s for s in resume_tool_specs(_snap())}
    all_p = json.loads(await specs["resume_get_section"].handler({"section": "projects"}))
    assert len(all_p["data"]) == 3
    filtered = json.loads(
        await specs["resume_get_section"].handler({"section": "projects", "focus": "p1"})
    )
    assert len(filtered["data"]) == 1


@pytest.mark.asyncio
async def test_get_section_skills_summary_links() -> None:
    specs = {s.name: s for s in resume_tool_specs(_snap())}
    skills = json.loads(await specs["resume_get_section"].handler({"section": "skills"}))
    assert "Python" in skills["data"]["skills"]
    summary = json.loads(await specs["resume_get_section"].handler({"section": "summary"}))
    assert summary["data"]["summary"] == "great"
    links = json.loads(await specs["resume_get_section"].handler({"section": "links"}))
    assert "github.com" in links["data"]["github_urls"][0]


@pytest.mark.asyncio
async def test_get_section_raw_paging() -> None:
    snap = _snap(raw_text="0123456789" * 1000)
    specs = {s.name: s for s in resume_tool_specs(snap)}
    page = json.loads(
        await specs["resume_get_section"].handler({"section": "raw", "offset": 5, "limit": 300})
    )
    assert page["data"]["offset"] == 5
    assert page["data"]["limit"] == 300
    assert page["data"]["total_chars"] == 10000
    # Limit clamping: tiny -> 200, huge -> hard cap.
    tiny = json.loads(await specs["resume_get_section"].handler({"section": "raw", "limit": 1}))
    assert tiny["data"]["limit"] == 200
    huge = json.loads(
        await specs["resume_get_section"].handler({"section": "raw", "limit": 999999})
    )
    assert huge["data"]["limit"] == resume_mod.RESUME_RAW_PAGE_HARD_CHARS
    bad = json.loads(
        await specs["resume_get_section"].handler({"section": "raw", "limit": "bad"})
    )
    assert bad["data"]["limit"] == resume_mod.RESUME_RAW_PAGE_CHARS
    # Negative offset clamped, EOF flag.
    neg = json.loads(
        await specs["resume_get_section"].handler({"section": "raw", "offset": -5, "limit": 200})
    )
    assert neg["data"]["offset"] == 0
    eof = json.loads(
        await specs["resume_get_section"].handler({"section": "raw", "offset": 9900, "limit": 500})
    )
    assert eof["data"]["eof"] is True


def test_section_order_constant() -> None:
    assert "raw" in resume_mod.RESUME_SECTION_ORDER
