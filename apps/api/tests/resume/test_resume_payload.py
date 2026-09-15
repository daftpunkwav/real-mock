"""Payload tests for src/realmock/domains/resume/agents/payload.py.

Covers: build_review_user_message docx-note branch, vision-success branch with
mocked file/render/context (has_visual_pages flag).
Conventions: no real network/model downloads (all clients mocked); file/render
helpers mocked; rate limits reset per test.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from realmock.platform.core.ratelimit import reset_rate_limit


@pytest.fixture(autouse=True)
def _clean_limits():
    reset_rate_limit()
    yield
    reset_rate_limit()


def test_payload_docx_note() -> None:
    from realmock.domains.resume.agents import payload as mod
    from realmock.platform.capabilities.ai.agent.tools.resume import ResumeSnapshot
    from realmock.platform.models import Resume

    snap2 = ResumeSnapshot(
        resume_id=1,
        filename="cv.docx",
        file_type="docx",
        raw_text="text",
        parsed={},
    )
    resume = MagicMock(spec=Resume)
    msg = asyncio.run(mod.build_review_user_message(resume, snap2, supports_vision=False))
    assert "Word" in str(msg["content"])


@pytest.mark.asyncio
async def test_payload_vision_success(monkeypatch) -> None:
    from realmock.domains.resume.agents import payload as mod
    from realmock.platform.capabilities.ai.agent.tools.resume import ResumeSnapshot

    snap = ResumeSnapshot(
        resume_id=1,
        filename="cv.pdf",
        file_type="pdf",
        raw_text="text",
        parsed={},
    )
    resume = MagicMock()
    resume.id = 1
    monkeypatch.setattr(mod, "find_resume_file", lambda r: "/tmp/cv.pdf")
    monkeypatch.setattr(
        mod, "render_pdf_pages_as_data_urls", lambda path, max_pages=1: ["data:url1"]
    )
    monkeypatch.setattr(mod, "select_vision_urls", lambda urls, ctx: urls)
    monkeypatch.setattr(mod, "resolve_context_window", lambda ctx: 100000)
    out = await mod.build_review_user_message(resume, snap, supports_vision=True)
    assert isinstance(out["content"], list)
    assert snap.has_visual_pages is True
