"""Reference outline service (WS mixin)."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from realmock.domains.interview.services.interview.agent_text import strip_markers, strip_think_blocks

if TYPE_CHECKING:
    from realmock.domains.interview.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)


class ReferenceHintMixin:
    """Generate a reference outline. Depends on ctx.session_id / ctx.llm / ctx.agent / ctx.hint_inflight / send."""

    ctx: ConnectionContext

    _HINT_TIMEOUT_SEC: float = 20.0
    _HINT_CTX_CHARS: int = 1200

    async def _on_request_hint(self, data: dict[str, Any]) -> None:
        """In-memory + LLM only; no DB access."""
        question = strip_think_blocks((data.get("question") or "").strip())
        question = strip_markers(question)
        question = self._extract_hint_question(question)
        if not question or not self.ctx.llm:
            await self.send(
                "reference_hint",
                question=question or "",
                content="Could not generate a reference answer; outline points from your own experience.",
            )
            return
        key = question[:200]
        if self.ctx.hint_inflight == key:
            return
        self.ctx.hint_inflight = key
        try:
            await self.send("reference_hint_loading", question=question)
            try:
                hint = await asyncio.wait_for(
                    self._generate_reference_hint(question),
                    timeout=self._HINT_TIMEOUT_SEC,
                )
            except asyncio.TimeoutError:
                logger.warning("Reference hint timed out sid=%s", self.ctx.session_id)
                hint = (
                    "Generation timed out. Draft STAR bullets yourself: "
                    "Situation → Task → Action → Result (prefer quantified outcomes)."
                )
            except Exception as e:
                logger.warning("Reference hint error sid=%s: %s", self.ctx.session_id, e)
                hint = "Could not generate a reference answer; outline points from your own experience."
            hint = strip_markers(strip_think_blocks(hint or ""))
            if not hint.strip():
                hint = "Could not generate a reference answer; outline points from your own experience."
            await self.send("reference_hint", question=question, content=hint)
        finally:
            if self.ctx.hint_inflight == key:
                self.ctx.hint_inflight = None

    @staticmethod
    def _extract_hint_question(text: str) -> str:
        """Extract the last question from the interviewer's entire response to control the quadratic LLM input volume."""
        t = (text or "").strip()
        if not t:
            return ""
        parts = [p.strip() for p in t.split("\n") if p.strip()]
        if not parts:
            return t[:500]
        for line in reversed(parts):
            if any(q in line for q in ("?", "？", "please", "introduce", "chat", "tell me")):
                return line[:500]
        return parts[-1][:500]

    async def _generate_reference_hint(self, question: str) -> str:
        """Generate a reference outline; only use in-memory dialogue and LLM, without RAG/DB access."""
        assert self.ctx.llm and self.ctx.agent
        system_ctx = ""
        for m in self.ctx.agent.messages:
            if m.get("role") == "system":
                system_ctx = str(m.get("content", ""))[: self._HINT_CTX_CHARS]
                break
        from realmock.platform.core.prompts import with_agent_output_rules

        messages = [
            {
                "role": "system",
                "content": with_agent_output_rules(
                    "You are an interview coach. From the candidate background, draft a concise "
                    "reference-answer outline for the interviewer's question.\n"
                    "Requirements: 3-5 bullets, one per line, starting with '- '; ground in resume "
                    "experience; keep it short; do not invent project details never mentioned; "
                    "do not output reasoning or <think> tags."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Candidate background summary:\n{system_ctx or '(no detailed profile yet)'}\n\n"
                    f"Interviewer question: {question}\n\nProvide a reference-answer outline:"
                ),
            },
        ]
        try:
            return await self.ctx.llm.chat(messages, temperature=0.4, max_tokens=400)
        except Exception as e:
            logger.warning("Reference hint generation failed: %s", e)
            return "Could not generate a reference answer; outline points from your own experience."
