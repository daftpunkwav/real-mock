"""Closing-speech prompts and phase jump (pure data/policy for InterviewRunner.stream_closing)."""

from __future__ import annotations

from realmock.domains.interview.agents.session_state import InterviewSessionState

# Closing tone hints by personality (preserve prior intent)
CLOSING_BY_PERSONALITY: dict[str, str] = {
    "gentle": "Warm and encouraging; affirm preparation and attitude; gently note 1–2 improvements.",
    "professional": "Professional and restrained; give a structured spoken review (strengths / gaps); thank them.",
    "pressure": "Keep some edge without being harsh; note how they handled pressure and weak spots; still thank them formally.",
    "hr": "Emphasize soft skills and culture-fit impressions; encourage follow-up; thank them.",
    "expert": "Comment on technical depth — highlights and gaps; thank them professionally.",
}


def closing_system_prompt(style_hint: str) -> str:
    """Build the system prompt for an early 'End interview' wrap-up."""
    nl = "\n"
    return (
        "The candidate clicked 'End interview'. Deliver a spoken wrap-up now: "
        "do not ask more questions or start a new assessment."
        + nl
        + "Requirements:"
        + nl
        + "1. Thank the candidate for joining this mock interview;"
        + nl
        + "2. In 3–6 sentences, give a personalized spoken summary and evaluation based on "
        "what was discussed (at least one strength and one improvement). If little was said, "
        "briefly comment on attitude and communication;"
        + nl
        + f"3. Personality and tone: {style_hint}"
        + nl
        + "4. Do not output tables or report headings; do not invent project details that were never mentioned;"
        + nl
        + "5. Set interview_complete to true in your reply;"
        + nl
        + "6. Judge the round yourself based on question difficulty, the target role/level, and whether "
        "this is an internship or a full-time position, then set \"verdict\" to \"passed\" or \"failed\" "
        "and announce the result naturally in your spoken summary"
    )


def jump_to_summary_phase(state: InterviewSessionState, phase_ids: list[str]) -> bool:
    """Jump phase index to the wrap-up step before closing; return whether jumped.

    Static flows jump to the ``summary`` phase id; agent-planned flows (whose
    ids are opaque) jump to the last step. Also resets the in-phase question
    count and syncs session.current_phase, matching runner behavior.
    """
    summary_idx = next(
        (i for i, pid in enumerate(phase_ids) if pid == "summary"),
        len(phase_ids) - 1,
    )
    summary_idx = max(0, summary_idx)
    if state.current_phase_idx < summary_idx:
        state.current_phase_idx = summary_idx
        state.questions_in_phase = 0
        state.session.current_phase = phase_ids[summary_idx]
        return True
    return False


__all__ = [
    "CLOSING_BY_PERSONALITY",
    "closing_system_prompt",
    "jump_to_summary_phase",
]
