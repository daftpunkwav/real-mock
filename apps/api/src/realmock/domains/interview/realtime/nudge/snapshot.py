"""Session snapshot: container for the latest state written by each turn participant.

Owned by the realtime nudge layer (the owner is :class:`realmock.domains.interview.realtime.nudge.orchestrator.InterviewOrchestrator`).
The realtime layer only writes (vision/STT data) and reads it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class SessionSnapshot:
    """The latest state snapshot written by each Agent."""

    stt_partial: str = ""
    stt_final: str = ""
    vision_summary: str = ""
    face_analysis: dict[str, Any] = field(default_factory=dict)
    last_user_text: str = ""
    token_usage: int = 0
    phase: str = ""
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def merge_face(self, face: dict[str, Any] | None) -> None:
        """Fold one face-analysis frame into the snapshot (no-op on empty)."""
        if not isinstance(face, dict) or not face:
            return
        self.face_analysis = face
        hints: list[str] = []
        if not face.get("face_detected", True):
            hints.append("No face detected")
        elif face.get("looking_away"):
            hints.append("Not looking at the camera")
        # Inbound frames are untrusted: FaceDetector degenerates to null and a
        # non-numeric nervousness must not raise out of the WS dispatch loop.
        nervousness = face.get("nervousness", 0)
        if isinstance(nervousness, (int, float)) and nervousness > 0.5:
            hints.append("Slightly nervous")
        if hints:
            self.vision_summary = "Candidate status: " + "; ".join(hints)
        self.updated_at = datetime.now(timezone.utc)


__all__ = ["SessionSnapshot"]
