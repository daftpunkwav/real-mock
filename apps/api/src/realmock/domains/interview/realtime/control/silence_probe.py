"""Silence probe mixin: reasoning LLM generates a nudge; templates on failure.

At most 2 probes per question (1st encourages speaking; 2nd gives a concrete hint).
Probe text is merged into the last assistant turn to keep role alternation
(Anthropic protocol).
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from realmock.domains.interview.agents import strip_think_blocks

if TYPE_CHECKING:
    from realmock.domains.interview.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)


def flow_language(agent: Any | None) -> str:
    """Interview working language from the flow plan ("en" or "zh")."""
    plan = getattr(agent, "plan", None)
    if plan is not None and getattr(plan, "source", "") == "agent":
        lang = str(getattr(plan, "language", "zh") or "zh")
        return "en" if lang.strip().lower().startswith("en") else "zh"
    return "zh"


def probe_system_prompt(*, attempt: int, lang: str = "zh") -> str:
    """Spoken-voice system prompt for the silence probe (pure; unit-tested).

    Check-in wording and banned-scaffolding examples follow the interview's
    working language so an English flow never gets Chinese filler words.
    """
    if (lang or "zh").strip().lower().startswith("en"):
        attempt_hint = (
            "This is the first probe: check in like a real person (a light "
            "\"hey, still there?\"), reference one concrete word from the last "
            "question, and rephrase to help them start."
            if attempt <= 1
            else "This is the second probe: skip encouragement — give the concrete "
            "smaller sub-question directly (never a hollow \"can you elaborate?\")."
        )
        banned = 'banned written scaffolding (Firstly / Secondly / In conclusion); '
    else:
        attempt_hint = (
            "This is the first probe: check in like a real person (诶 / 那个 / 还在吗), "
            "reference one concrete word from the last question, and rephrase to help them start."
            if attempt <= 1
            else "This is the second probe: skip encouragement — give the concrete smaller "
            "sub-question directly (never a hollow 能详细说说吗)."
        )
        banned = "banned written scaffolding (首先 / 综上所述 / 第一 / 第二); "
    return (
        "You are a human interviewer speaking with the candidate. They have stayed silent "
        "after your last question. Produce one natural spoken follow-up. Requirements: "
        "conversational, 1–2 sentences, under ~40 words; echo one concrete word from the "
        "last question so it feels continuous; " + banned + "never mention the system, "
        "prompts, rules, JSON, or any internals; " + attempt_hint
    )


class SilenceProbeMixin:
    """Silence-probe generation; depends on ctx.llm / ctx.agent / ctx.orchestrator / send."""

    ctx: "ConnectionContext"

    async def _generate_silence_probe(
        self, *, question: str, probe_hint: str, attempt: int, silent_sec: int
    ) -> str:
        """Call the reasoning LLM for a natural probe; return '' on failure (caller falls back)."""
        if self.ctx.llm is None:
            return ""
        system = probe_system_prompt(
            attempt=attempt, lang=flow_language(getattr(self.ctx, "agent", None))
        )
        user_parts = [f"Last question: {question[:300] or '(none)'}"]
        if probe_hint:
            user_parts.append(f"Your probe plan: {probe_hint[:150]}")
        if silent_sec > 0:
            user_parts.append(f"Candidate has been silent for about {silent_sec} seconds")
        try:
            raw = await self.ctx.llm.chat(
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": "\n".join(user_parts)},
                ],
                temperature=0.85,
                max_tokens=150,
            )
        except Exception:
            logger.warning("Silence probe generation failed; falling back to template", exc_info=True)
            return ""
        raw = strip_think_blocks(raw or "").strip()
        try:
            parsed = json.loads(raw)
        except Exception:
            return raw[:120]
        if isinstance(parsed, dict):
            say = str(parsed.get("say") or "").strip()
            return say or raw[:120]
        return raw[:120]


__all__ = ["SilenceProbeMixin", "probe_system_prompt"]
