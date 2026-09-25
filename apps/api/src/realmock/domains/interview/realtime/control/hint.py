"""Reference answer service (WS mixin): fast outline + detailed agent-loop answer.

Two modes (per-session ``reference_detail`` setting, default ``outline``):
- outline: one single-shot LLM call, 3-5 bullets, ~seconds.
- full: tool-grounded loop (profile / resume / GitHub) + first-person model
  answer via :mod:`realmock.domains.interview.agents.hint.hint_answer`.

Every request path ends with exactly one terminal event (``reference_hint``
or ``reference_hint_error``) so the room UI never gets stuck loading.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from realmock.domains.interview.agents import (
    generate_full_reference_hint,
    strip_markers,
    strip_think_blocks,
)
from realmock.domains.interview.realtime.control.prompts import reference_hint_coach
from realmock.platform.database import SessionLocal

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from realmock.domains.interview.models import InterviewSession
    from realmock.domains.interview.realtime.core.context import ConnectionContext

logger = logging.getLogger(__name__)

_OUTLINE_TIMEOUT_SEC = 20.0
_FULL_TIMEOUT_SEC = 75.0
_HINT_CTX_CHARS = 1200

_FALLBACK = {
    # (empty, timeout, error) triplets per flow language.
    "zh": (
        "暂时无法生成参考回答，请根据自己的经历组织要点。",
        "生成超时。可先按 STAR 自行组织：情境 → 任务 → 行动 → 结果（尽量量化）。",
        "暂时无法生成参考回答，请根据自己的经历组织要点。",
    ),
    "en": (
        "Could not generate a reference answer; outline points from your own experience.",
        "Generation timed out. Draft STAR bullets yourself: "
        "Situation → Task → Action → Result (prefer quantified outcomes).",
        "Could not generate a reference answer; outline points from your own experience.",
    ),
}

_RATE_LIMITED = {
    "zh": "请求太频繁，稍后再点“重新生成”。",
    "en": "Too many requests; tap regenerate again in a bit.",
}


class ReferenceHintMixin:
    """Generate reference answers. Depends on ctx.session_id / ctx.llm / ctx.agent / ctx.hint_inflight / ctx.reference_detail / send."""

    ctx: ConnectionContext

    if TYPE_CHECKING:
        # Members provided by sibling mixins of the composed InterviewWSHandler.
        send: Callable[..., Coroutine[Any, Any, None]]
        _load_session: Callable[..., InterviewSession | None]

    _HINT_CTX_CHARS: int = _HINT_CTX_CHARS

    # -- helpers ---------------------------------------------------------

    def _hint_language(self) -> str:
        """Flow language for hint copy ("en" or "zh")."""
        agent = self.ctx.agent
        plan = getattr(agent, "plan", None) if agent is not None else None
        if plan is not None and getattr(plan, "source", "") == "agent":
            lang = str(getattr(plan, "language", "zh") or "zh")
            return "en" if lang.strip().lower().startswith("en") else "zh"
        return "zh"

    def _hint_background(self) -> str:
        """Candidate material slice from the in-memory system prompt.

        The system prompt opens with persona/spoken-voice rules, so a raw
        head slice carries no resume content; cut the interview-setup and
        candidate grounding area instead (falls back to the head when the
        prompt shape is unrecognized).
        """
        agent = self.ctx.agent
        messages = getattr(agent, "messages", None) or []
        for m in messages:
            if isinstance(m, dict) and m.get("role") == "system":
                content = str(m.get("content", ""))
                return self._candidate_slice(content)
        return ""

    @staticmethod
    def _candidate_slice(content: str, limit: int = _HINT_CTX_CHARS) -> str:
        """Cut the setup/company/candidate area out of the system prompt."""
        start = -1
        for marker in (
            "## Interview setup",
            "## Candidate profile",
            "## Parsed resume",
            "## Candidate (compact",
        ):
            idx = content.find(marker)
            if idx >= 0 and (start < 0 or idx < start):
                start = idx
        if start < 0:
            return content[:limit]
        end = content.find("## Current phase")
        if end <= start:
            return content[start : start + limit]
        return content[start:end][:limit]

    # -- entry -----------------------------------------------------------

    async def _on_request_hint(self, data: dict[str, Any]) -> None:
        """In-memory + LLM only; the full mode opens one short-lived DB session for tools."""
        lang = self._hint_language()
        empty_fb, timeout_fb, error_fb = _FALLBACK[lang]
        question = strip_markers(strip_think_blocks((data.get("question") or "").strip()))
        question = self._extract_hint_question(question)
        if not question or not self.ctx.llm:
            await self.send("reference_hint", question=question or "", content=empty_fb)
            return
        key = question[:200]
        detailed = (self.ctx.reference_detail or "outline") == "full"
        if self.ctx.hint_inflight == key:
            # Same question already generating: re-announce loading so the UI
            # stays truthful; the in-flight run still delivers the terminal event.
            await self.send(
                "reference_hint_loading", question=question, detailed=detailed
            )
            return
        self.ctx.hint_inflight = key
        try:
            await self.send(
                "reference_hint_loading", question=question, detailed=detailed
            )
            try:
                if detailed:
                    hint = await asyncio.wait_for(
                        self._generate_full_reference_hint(question),
                        timeout=_FULL_TIMEOUT_SEC,
                    )
                    if not (hint or "").strip():
                        # Detailed loop came up empty: degrade to the fast outline
                        # within the same request instead of failing.
                        hint = await asyncio.wait_for(
                            self._generate_reference_hint(question),
                            timeout=_OUTLINE_TIMEOUT_SEC,
                        )
                else:
                    hint = await asyncio.wait_for(
                        self._generate_reference_hint(question),
                        timeout=_OUTLINE_TIMEOUT_SEC,
                    )
            except asyncio.TimeoutError:
                logger.warning("Reference hint timed out sid=%s", self.ctx.session_id)
                hint = timeout_fb
            except Exception as e:
                logger.warning("Reference hint error sid=%s: %s", self.ctx.session_id, e)
                hint = error_fb
            hint = strip_markers(strip_think_blocks(hint or ""))
            if not hint.strip():
                hint = error_fb
            await self.send("reference_hint", question=question, content=hint)
        finally:
            if self.ctx.hint_inflight == key:
                self.ctx.hint_inflight = None

    def _hint_rate_limited(self, data: dict[str, Any]) -> Any:
        """Terminal error event for hint rate-limiting (never leave the UI loading)."""
        lang = self._hint_language()
        question = strip_markers(
            strip_think_blocks((data.get("question") or "").strip())
        )
        return self.send(
            "reference_hint_error",
            question=self._extract_hint_question(question),
            message=_RATE_LIMITED[lang],
        )

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

    # -- outline (fast single-shot) --------------------------------------

    async def _generate_reference_hint(self, question: str) -> str:
        """Generate a reference outline; only use in-memory dialogue and LLM, without RAG/DB access."""
        assert self.ctx.llm and self.ctx.agent
        lang = self._hint_language()
        system_ctx = self._hint_background()
        from realmock.platform.core.prompts import with_agent_output_rules

        coach = reference_hint_coach(lang)
        if lang == "en":
            user_content = (
                f"Candidate background summary:\n{system_ctx or '(no detailed profile yet)'}\n\n"
                f"Interviewer question: {question}\n\nProvide a reference-answer outline:"
            )
        else:
            user_content = (
                f"候选人背景摘要：\n{system_ctx or '(暂无详细画像)'}\n\n"
                f"面试官问题：{question}\n\n请给出参考回答提纲："
            )
        messages = [
            {"role": "system", "content": with_agent_output_rules(coach)},
            {"role": "user", "content": user_content},
        ]
        try:
            return await self.ctx.llm.chat(messages, temperature=0.4, max_tokens=400)
        except Exception as e:
            logger.warning("Reference hint generation failed: %s", e)
            return _FALLBACK[lang][2]

    # -- full (tool-grounded loop) ---------------------------------------

    async def _generate_full_reference_hint(self, question: str) -> str | None:
        """Detailed mode: evidence-gathering loop + first-person model answer.

        Opens one short-lived DB session for tools; failures yield None so the
        caller degrades to the fast outline. The session row is only read
        (tool findings accumulate in the in-memory agent_state).
        """
        assert self.ctx.llm and self.ctx.agent
        db = SessionLocal()
        try:
            session = self._load_session(db)
            if session is None:
                return None
            return await generate_full_reference_hint(
                llm=self.ctx.llm,
                db=db,
                session=session,
                agent_state=self.ctx.agent.agent_state,
                question=question,
                background=self._hint_background(),
                flow_language=self._hint_language(),
            )
        finally:
            try:
                db.close()
            except Exception:
                logger.debug(
                    "hint DB close failed sid=%s", self.ctx.session_id, exc_info=True
                )
