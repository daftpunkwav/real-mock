"""Turn side effects: interruption, closing, and silence follow-up (WS mixin composition).

Responsibilities are split into independent submodules; this module only composes the mixins:

- :mod:`interrupt_control` — interruption counting and handling;
- :mod:`user_text_control` — admit user text into a turn;
- :mod:`finish_control` — proactive closing;
- :mod:`silence_nudge` — silence follow-up orchestration (LLM generation remains in :mod:`silence_probe`).
"""

from __future__ import annotations

from realmock.domains.interview.realtime.control.finish import FinishControlMixin
from realmock.domains.interview.realtime.control.interrupt import InterruptControlMixin
from realmock.domains.interview.realtime.control.silence_nudge import SilenceNudgeMixin
from realmock.domains.interview.realtime.control.silence_probe import SilenceProbeMixin
from realmock.domains.interview.realtime.control.user_text import UserTextControlMixin


class TurnControlMixin(
    InterruptControlMixin,
    UserTextControlMixin,
    FinishControlMixin,
    SilenceNudgeMixin,
    SilenceProbeMixin,
):
    """Talk turn side effect combination; relies on status fields in ctx + inherited methods."""


__all__ = ["TurnControlMixin"]
