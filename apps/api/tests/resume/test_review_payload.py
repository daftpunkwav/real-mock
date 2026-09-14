"""Prior-version reference blocks in the resume-review user message."""

from __future__ import annotations

import json

from realmock.domains.resume.agents.payload import build_review_user_message
from realmock.domains.resume.schemas.limits import DIMENSION_KEYS
from realmock.domains.resume.services import resume_mappers, store
from realmock.domains.resume.services.score_anchor import calibration_text, compact_score_anchor
from realmock.platform.capabilities.ai.agent.tools.resume import ResumeSnapshot
from realmock.platform.schemas import CandidateProfile


def _scored_analysis() -> str:
    dims = {key: {"score": 70, "comment": "ok"} for key in DIMENSION_KEYS}
    return json.dumps(
        {
            "score": 70,
            "dimension_scores": dims,
            "strengths": ["metrics", "ownership", "stack"],
            "weaknesses": ["layout", "keywords", "gaps"],
        }
    )


def _snapshot(row) -> ResumeSnapshot:
    return ResumeSnapshot(
        resume_id=int(row.id),
        filename=row.filename,
        file_type="txt",
    )


async def test_same_file_re_review_shows_no_prior_scores(api_db) -> None:
    """Same-file re-reviews score from current evidence alone: no score block."""
    row = store.insert_upload(
        api_db,
        filename="cv.txt",
        file_type="txt",
        raw_text="body",
        parsed=CandidateProfile(name="Ada"),
    )
    row.analysis = _scored_analysis()
    api_db.commit()
    api_db.refresh(row)

    assert calibration_text() == ""
    message = await build_review_user_message(
        row, _snapshot(row), supports_vision=False, calibration=""
    )
    text = message["content"]
    assert "Prior scored version" not in text
    assert "±" not in text
    assert "cv.txt" in text  # resume evidence still present


async def test_new_version_adds_prior_version_scores(api_db) -> None:
    v1 = store.insert_upload(
        api_db,
        filename="cv.txt",
        file_type="txt",
        raw_text="v1",
        parsed=CandidateProfile(name="Ada"),
    )
    v1.analysis = _scored_analysis()
    api_db.commit()
    v2 = store.insert_upload(
        api_db,
        filename="cv-v2.txt",
        file_type="txt",
        raw_text="v2",
        parsed=CandidateProfile(name="Ada"),
        family_id=v1.family_id,
    )
    cal = calibration_text(
        previous_analysis=resume_mappers.load_analysis_dict(v1.analysis, v1.id),
        previous_version_n=v1.version_n,
    )
    message = await build_review_user_message(
        v2, _snapshot(v2), supports_vision=False, calibration=cal
    )
    text = message["content"]
    assert "Prior scored version" in text
    assert "never a target" in text
    assert "v1" in text
    assert "THIS same file" not in text


def test_no_prior_version_yields_empty_block() -> None:
    current = json.loads(_scored_analysis())
    assert calibration_text(previous_analysis=None, previous_version_n=None) == ""
    assert calibration_text(previous_analysis={"score": 1}, previous_version_n=None) == ""
    # Thin prior coverage also yields nothing, even with a version number.
    assert calibration_text(previous_analysis=current, previous_version_n=None) == ""


def test_compact_anchor_requires_enough_dimensions() -> None:
    assert compact_score_anchor({"dimension_scores": {"a": {"score": 1}}}) is None
    assert compact_score_anchor({"dimension_scores": {f"d{i}": {"score": 50} for i in range(4)}}) is not None


def test_review_calibration_lookup_uses_prior_version(api_db) -> None:
    from realmock.domains.resume.agents.review import _calibration_for_review

    v1 = store.insert_upload(
        api_db,
        filename="cv.txt",
        file_type="txt",
        raw_text="v1",
        parsed=CandidateProfile(name="Ada"),
    )
    v1.analysis = _scored_analysis()
    api_db.commit()
    v2 = store.insert_upload(
        api_db,
        filename="cv-v2.txt",
        file_type="txt",
        raw_text="v2",
        parsed=CandidateProfile(name="Ada"),
        family_id=v1.family_id,
    )
    text = _calibration_for_review(v2, api_db)
    assert "Prior scored version" in text
    assert "THIS same file" not in text


def test_scored_file_without_family_yields_no_calibration(api_db) -> None:
    """Same-file scores alone never anchor: no prior version, no block."""
    from realmock.domains.resume.agents.review import _calibration_for_review

    row = store.insert_upload(
        api_db,
        filename="solo.txt",
        file_type="txt",
        raw_text="solo",
        parsed=CandidateProfile(name="Ada"),
    )
    row.analysis = _scored_analysis()
    api_db.commit()
    assert _calibration_for_review(row, api_db) == ""


def test_overview_contact_falls_back_to_raw_text() -> None:
    """Parse gaps must not read as missing contact info in the first message."""
    from realmock.domains.resume.agents.payload import _overview_text

    snapshot = ResumeSnapshot(
        resume_id=1,
        filename="r.pdf",
        file_type="pdf",
        raw_text="Contact ada@example.com 13800138000 https://github.com/ada/app",
        parsed={},
    )
    intro = _overview_text(snapshot)
    assert "ada@example.com" in intro
    assert "13800138000" in intro
    assert "https://github.com/ada/app" in intro


async def test_visual_status_tracks_degradation(monkeypatch) -> None:
    from types import SimpleNamespace

    from realmock.domains.resume.agents import payload as payload_module

    resume = SimpleNamespace(id=7)

    async def build(file_type: str, *, vision: bool) -> ResumeSnapshot:
        snapshot = ResumeSnapshot(resume_id=7, filename="r.pdf", file_type=file_type)
        await build_review_user_message(resume, snapshot, supports_vision=vision)
        return snapshot

    assert (await build("txt", vision=True)).visual_status == "ok"
    assert (await build("pdf", vision=False)).visual_status == "no_vision"

    monkeypatch.setattr(payload_module, "find_resume_file", lambda _resume: None)
    assert (await build("pdf", vision=True)).visual_status == "missing_file"

    from pathlib import Path

    monkeypatch.setattr(payload_module, "find_resume_file", lambda _resume: Path("r.pdf"))

    def _boom(_path, **_kwargs):
        raise RuntimeError("no renderer")

    monkeypatch.setattr(payload_module, "render_pdf_pages_as_data_urls", _boom)
    assert (await build("pdf", vision=True)).visual_status == "render_failed"

    monkeypatch.setattr(
        payload_module, "render_pdf_pages_as_data_urls", lambda _p, **_k: ["data:img"]
    )
    monkeypatch.setattr(payload_module, "select_vision_urls", lambda urls, _w: [])
    assert (await build("pdf", vision=True)).visual_status == "filtered"


def test_vision_notice_message_matrix() -> None:
    from realmock.domains.resume.agents.review import _vision_notice_message

    assert (
        _vision_notice_message(locale="en", file_type="pdf", visual_status="ok") is None
    )
    assert (
        _vision_notice_message(locale="zh-CN", file_type="txt", visual_status="no_vision")
        is None
    )
    assert (
        _vision_notice_message(locale="zh-CN", file_type="pdf", visual_status="bogus")
        is None
    )
    zh = _vision_notice_message(
        locale="zh-CN", file_type="pdf", visual_status="render_failed"
    )
    en = _vision_notice_message(locale="en", file_type="pdf", visual_status="no_vision")
    assert zh is not None and "纯文本评审" in zh
    assert en is not None and "text-only review" in en
