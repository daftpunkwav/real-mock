"""Visual Agent: Aggregates candidate video status."""

from typing import Any


class VisionAgent:
    """Merge facial analysis with optional frame summarization into text states."""

    @staticmethod
    def summarize(face_analysis: dict[str, Any] | None) -> str:
        """Compress one face-analysis frame into a short English state line.

        Args:
            face_analysis: Raw frame dict (``face_detected`` / ``looking_away`` /
                ``nervousness`` / ``face_count``); None or empty yields ``""``.

        Returns:
            Semicolon-joined hints, or a normal-state sentence when unremarkable.
        """
        if not isinstance(face_analysis, dict) or not face_analysis:
            return ""
        hints: list[str] = []
        if not face_analysis.get("face_detected", True):
            hints.append("No face detected in the picture")
        elif face_analysis.get("looking_away"):
            hints.append("Candidate not looking directly into the camera")
        nervousness = face_analysis.get("nervousness", 0)
        if isinstance(nervousness, (int, float)) and nervousness > 0.5:
            hints.append("Candidate appears nervous")
        face_count = face_analysis.get("face_count", 1)
        if isinstance(face_count, (int, float)) and face_count > 1:
            hints.append("Multiple people appear on the screen")
        return "; ".join(hints) if hints else "Candidate status is normal"
