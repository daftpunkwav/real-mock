"""SessionSnapshot face folding: untrusted client frames must not raise.

Conventions: plain unit tests, no WS stack — merge_face is called straight from
the vision_update dispatch path, so a degenerate field must degrade silently.
"""

from __future__ import annotations

from realmock.domains.interview.realtime.nudge.snapshot import SessionSnapshot


def test_merge_face_records_status_hints() -> None:
    snap = SessionSnapshot()
    snap.merge_face({"face_detected": True, "nervousness": 0.9})
    assert "Slightly nervous" in snap.vision_summary

    snap.merge_face({"face_detected": False})
    assert "No face detected" in snap.vision_summary


def test_merge_face_ignores_non_numeric_nervousness() -> None:
    """FaceDetector degenerates to null and the protocol has no field schema."""
    for bad in (None, "high", {}):
        snap = SessionSnapshot()
        snap.merge_face({"face_detected": True, "nervousness": bad})
        assert snap.vision_summary == ""
        assert snap.face_analysis == {"face_detected": True, "nervousness": bad}


def test_merge_face_empty_or_non_object_frame_is_noop() -> None:
    """The protocol only declares face_analysis as an object; a scalar must not raise."""
    for bad in (None, {}, "x", [1, 2], 123, True):
        snap = SessionSnapshot()
        snap.merge_face(bad)  # type: ignore[arg-type]
        assert snap.face_analysis == {}
        assert snap.vision_summary == ""
