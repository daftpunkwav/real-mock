"""Silence probe mixin: reasoning LLM generates a nudge; templates on failure.

At most 2 probes per question (1st encourages speaking; 2nd gives a concrete hint).
Probe text is merged into the last assistant turn to keep role alternation
(Anthropic protocol).
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from realmock.domains.interview.agents import strip_think_blocks

if TYPE_CHECKING:
    from realmock.domains.interview.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)


class SilenceProbeMixin:
    """Silence-probe generation; depends on ctx.llm / ctx.agent / ctx.orchestrator / send."""

    ctx: "ConnectionContext"

    async def _generate_silence_probe(
        self, *, question: str, probe_hint: str, attempt: int, silent_sec: int
    ) -> str:
        """Call the reasoning LLM for a natural probe; return '' on failure (caller falls back)."""
        if self.ctx.llm is None:
            return ""
        attempt_hint = (
            "This is the first probe: encourage them or rephrase to help them start speaking."
            if attempt <= 1
            else "This is the second probe: give a concrete hint, or break the question into a smaller sub-question."
        )
        system = (
            "You are a human interviewer speaking with the candidate. They have stayed silent "
            "after your last question. Produce one natural spoken follow-up. Requirements: "
            "conversational, 1–2 sentences, under ~40 words; never mention the system, prompts, "
            "rules, JSON, or any internals; " + attempt_hint
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


__all__ = ["SilenceProbeMixin"]
