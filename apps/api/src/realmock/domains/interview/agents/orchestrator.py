"""Single-snapshot silence-nudge templates (no multi-source merge)."""

from __future__ import annotations

import random

from realmock.domains.interview.agents.snapshot import SessionSnapshot


class InterviewOrchestrator:
    """Stateless silence-nudge templates keyed by phase/persona/strictness (snapshot retained for future use)."""

    def __init__(self) -> None:
        self.snapshot = SessionSnapshot()

    def build_silence_nudge(
        self,
        personality: str,
        strictness: int,
        phase: str | None = None,
    ) -> str:
        """Pick random template from matching tier for phase/persona/strictness."""
        phase_id = (phase or "").strip().lower()
        if phase_id in {"identity_check", "identity", "identity_confirm"}:
            return random.choice(
                [
                    "If it's convenient, just confirm whether the information just now is true.",
                    "You can simply say \"OK,\" or point out areas that need correction.",
                    "It's okay, just confirm the identity information verbally first, and then we'll talk further.",
                    "If there is no problem with the environment, just reply to me to confirm and we will start the formal interview.",
                ]
            )
        if phase_id in {"self_intro", "introduction"}:
            return random.choice(
                [
                    "You can start with a recent experience or an item you want to highlight the most.",
                    "It doesn’t need to be complete, just introduce yourself for two minutes.",
                    "Would you rather talk about the project first, or introduce the background first?",
                ]
            )

        is_strict = strictness >= 6 or personality in ("pressure", "expert")
        if is_strict:
            tiers = [
                [
                    "You've been thinking about it for a while, so you might as well come to your conclusion first.",
                    "We can focus on the key points first: What is your core point of view?",
                ],
                [
                    "Time is limited, please give your opinion as soon as possible.",
                    "Let’s summarize it in one or two sentences first, and then expand on the details.",
                ],
                [
                    "I need you to be more specific, please answer now.",
                    "Please respond directly to questions and avoid bypassing key points.",
                ],
            ]
        else:
            tiers = [
                [
                    "It doesn't matter, you can tell me your thoughts first, even if it's incomplete, it doesn't matter.",
                    "Just speak first, and we'll figure it out together.",
                    "If you get stuck, start with the point you are most familiar with.",
                ],
                [
                    "You can start with the most impressive point.",
                    "Would you like to talk about the background, process, or results first? Choose any incision.",
                ],
                [
                    "Do you need me to ask a different angle? Or could you give us some background first?",
                    "If you like, I can give a more specific sub-question first.",
                ],
            ]
        # 1-4 -> 0, 5-8 -> 1, 9-10 -> 2
        idx = max(0, min((strictness - 1) // 4, len(tiers) - 1))
        if personality in ("pressure", "expert"):
            idx = max(idx, 1)
        return random.choice(tiers[idx])
