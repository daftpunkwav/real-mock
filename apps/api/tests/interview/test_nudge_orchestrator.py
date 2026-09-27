# -*- coding: utf-8 -*-
"""Silence-nudge template selection (realtime/nudge/orchestrator.py).

``InterviewOrchestrator.build_silence_nudge`` picks a spoken fallback line:
phase-specific branches first (identity / self-intro), then a strictness
tier — tier index derives from strictness bands (1-4 → 0, 5-8 → 1, 9-10 → 2)
and pressure/expert personas never fall below tier 1. These tests pin the
selection boundaries with ``random.seed`` so every branch is deterministic.
"""

from __future__ import annotations

import random

from realmock.domains.interview.realtime.nudge.orchestrator import (
    InterviewOrchestrator,
)

_IDENTITY_LINES = (
    "If it's convenient, just confirm whether the information just now is true.",
    'You can simply say "OK," or point out areas that need correction.',
    "It's okay, just confirm the identity information verbally first, and then we'll talk further.",
    "If there is no problem with the environment, just reply to me to confirm and we will start the formal interview.",
)
_SELF_INTRO_LINES = (
    "You can start with a recent experience or an item you want to highlight the most.",
    "It doesn’t need to be complete, just introduce yourself for two minutes.",
    "Would you rather talk about the project first, or introduce the background first?",
)
_STRICT_TIER_LINES = (
    "You've been thinking about it for a while, so you might as well come to your conclusion first.",
    "We can focus on the key points first: What is your core point of view?",
    "Time is limited, please give your opinion as soon as possible.",
    "Let’s summarize it in one or two sentences first, and then expand on the details.",
    "I need you to be more specific, please answer now.",
    "Please respond directly to questions and avoid bypassing key points.",
)
_GENTLE_TIER_LINES = (
    "It doesn't matter, you can tell me your thoughts first, even if it's incomplete, it doesn't matter.",
    "Just speak first, and we'll figure it out together.",
    "If you get stuck, start with the point you are most familiar with.",
    "You can start with the most impressive point.",
    "Would you like to talk about the background, process, or results first? Choose any incision.",
    "Do you need me to ask a different angle? Or could you give us some background first?",
    "If you like, I can give a more specific sub-question first.",
)


def test_identity_phase_branch_wins_regardless_of_persona() -> None:
    random.seed(7)
    orch = InterviewOrchestrator()
    for personality in ("professional", "pressure"):
        for phase in ("identity_check", "identity", "identity_confirm"):
            assert orch.build_silence_nudge(personality, 3, phase=phase) in _IDENTITY_LINES


def test_self_intro_phase_branch() -> None:
    random.seed(7)
    orch = InterviewOrchestrator()
    for phase in ("self_intro", "introduction"):
        assert orch.build_silence_nudge("professional", 3, phase=phase) in _SELF_INTRO_LINES


def test_gentle_low_strictness_uses_first_tier() -> None:
    random.seed(7)
    orch = InterviewOrchestrator()
    line = orch.build_silence_nudge("professional", 2, phase="project_deep_dive")
    assert line in _GENTLE_TIER_LINES


def test_strict_persona_never_uses_first_tier() -> None:
    random.seed(7)
    orch = InterviewOrchestrator()
    for _ in range(20):
        line = orch.build_silence_nudge("pressure", 1, phase="project_deep_dive")
        assert line in _STRICT_TIER_LINES


def test_high_strictness_reaches_last_tier() -> None:
    random.seed(7)
    orch = InterviewOrchestrator()
    for _ in range(20):
        line = orch.build_silence_nudge("professional", 10, phase="summary")
        assert line in _STRICT_TIER_LINES


def test_none_phase_falls_into_strictness_tiers() -> None:
    random.seed(7)
    orch = InterviewOrchestrator()
    line = orch.build_silence_nudge("professional", 5, phase=None)
    assert line in _GENTLE_TIER_LINES
