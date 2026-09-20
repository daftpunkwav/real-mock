"""Vision agent tests for src/realmock/domains/interview/capabilities/vision/agent.py.

Covers: VisionAgent.summarize pure branches (no network)
Conventions: no real network/LLM (mocked or faked); deterministic asserts only
"""

from __future__ import annotations

import pytest

from realmock.domains.interview.capabilities.vision.agent import VisionAgent






























def test_vision_summarize_none_and_empty() -> None:
    assert VisionAgent.summarize(None) == ""
    assert VisionAgent.summarize({}) == ""


def test_vision_summarize_no_face() -> None:
    out = VisionAgent.summarize({"face_detected": False})
    assert "No face detected" in out


def test_vision_summarize_looking_away() -> None:
    out = VisionAgent.summarize({"face_detected": True, "looking_away": True})
    assert "not looking directly" in out


def test_vision_summarize_nervous() -> None:
    out = VisionAgent.summarize({"face_detected": True, "nervousness": 0.9})
    assert "nervous" in out
    calm = VisionAgent.summarize({"face_detected": True, "nervousness": 0.1})
    assert calm == "Candidate status is normal"


def test_vision_summarize_nervous_non_numeric_ignored() -> None:
    out = VisionAgent.summarize({"face_detected": True, "nervousness": "high"})
    assert out == "Candidate status is normal"


def test_vision_summarize_multiple_faces() -> None:
    out = VisionAgent.summarize({"face_detected": True, "face_count": 2})
    assert "Multiple people" in out


def test_vision_summarize_face_count_non_numeric_ignored() -> None:
    """A client frame may carry null/str; it must not raise out of the WS loop."""
    for bad in (None, "3", {}):
        out = VisionAgent.summarize({"face_detected": True, "face_count": bad})
        assert out == "Candidate status is normal"


def test_vision_summarize_normal() -> None:
    assert VisionAgent.summarize({"face_detected": True}) == "Candidate status is normal"


def test_vision_summarize_combined_hints_joined() -> None:
    out = VisionAgent.summarize(
        {"face_detected": True, "looking_away": True, "nervousness": 0.8, "face_count": 3}
    )
    assert "; " in out
    assert "not looking directly" in out
    assert "nervous" in out
    assert "Multiple people" in out


@pytest.mark.asyncio
async def test_vision_summarize_no_network_needed() -> None:
    # Pure function: no httpx/LLM touched.
    assert VisionAgent.summarize({"face_detected": True, "face_count": 1}) != ""


def test_vision_summarize_non_object_frame_ignored() -> None:
    from realmock.domains.interview.capabilities.vision.agent import VisionAgent

    for bad in (None, {}, "x", [1, 2], 123):
        assert VisionAgent.summarize(bad) == ""
