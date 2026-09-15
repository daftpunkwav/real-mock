"""Session prompt builder mixin: profile lookup, company context, structured memory.

Split from :class:`realmock.domains.interview.agents.session_state.InterviewSessionState`.
Single responsibility: build the system prompt and the per-turn memory section.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Literal, cast

from sqlalchemy.orm import Session

from realmock.platform.database import api_db_session, sessions_db_session
from realmock.platform.services.candidate_read import get_candidate_profile, get_user_profile
from realmock.domains.interview.models import InterviewProcess
from realmock.domains.interview.schemas import InterviewConfig
from realmock.platform.catalogs.company import get_company_context
from realmock.platform.capabilities.ai.agent import WorkingMemory
from realmock.domains.interview.agents.agent_prompts import (
    build_system_prompt,
    candidate_block,
    compact_candidate_block,
    needs_compact_candidate,
)
from realmock.domains.interview.agents.workflows import Workflow
from realmock.domains.interview.process.company_research import (
    blend_company_context,
    load_session_company_research,
)
from realmock.domains.interview.process.process_memory import load_memory, render_for_prompt
from realmock.domains.interview.process.round_chain import step_for

if TYPE_CHECKING:
    from realmock.domains.interview.agents.session_state import InterviewSessionState

logger = logging.getLogger(__name__)

#: Growth-insights provider port: returns a cross-interview summary dict.
#: Wired by the orchestrator (runner) to a growth implementation; this module
#: does not depend on the growth domain.
SystemInsightsProvider = Callable[..., dict[str, Any]]

_MEMORY_SECTION_MARKER = "## Session structured memory (do not repeat asked questions)"


class SessionPromptMixin:
    """System-prompt builder; depends on host state machine session / agent_state / workflow."""

    session: Any

    #: Growth feedback port; None means not wired (runner overwrites with the
    #: growth implementation at construction). To disable feedback in tests /
    #: deploys, set a stub that returns ``{}`` (e.g. ``lambda **kw: {}``);
    #: otherwise runner binds the default implementation.
    system_insights_provider: SystemInsightsProvider | None = None

    if TYPE_CHECKING:
        _self: InterviewSessionState

    # ---- Config / context lookups (read-only) --------------------------------

    def get_config(self) -> InterviewConfig:
        """Validated interview config from the session row (legacy free-form tolerated)."""
        # DB fields are free-form str and may hold legacy values; cast to Literal
        # and let Pydantic validate.
        return InterviewConfig(
            role=self.session.role,
            level=self.session.level,
            company=self.session.company,
            workflow_type=cast(
                Literal["technical", "hr", "management"],
                self.session.workflow_type or "technical",
            ),
            personality=cast(
                Literal["gentle", "professional", "pressure", "hr", "expert"],
                self.session.personality or "professional",
            ),
            strictness=self.session.strictness,
            interview_style=cast(
                Literal["guided", "deep_dive", "continuous", "challenging"],
                self.session.interview_style or "deep_dive",
            ),
            resume_id=self.session.resume_id,
        )

    def get_user_profile(self, db: Session):
        """Candidate profile row for prompt grounding (None when absent)."""
        with api_db_session() as api_db:
            return get_user_profile(api_db, self.session.profile_id)

    def get_candidate(self, db: Session):
        """Candidate resume payload for prompt grounding (None when absent)."""
        with api_db_session() as api_db:
            return get_candidate_profile(api_db, self.session.resume_id)

    def _system_learning_section(self) -> str:
        """Extract a short cross-interview learning summary for this session.

        Implements the PRD 4.7 growth feedback loop: inject historical weak spots
        and effective probe clues for this company/role into the system prompt.
        Returns empty string when the provider is missing or fails.
        """
        provider = self.system_insights_provider
        if provider is None:
            return ""
        try:
            insights = provider(limit=5)
        except Exception as e:
            logger.warning("Failed to read system learning insights: %s", e)
            return ""

        parts: list[str] = []
        company = self.session.company or ""
        role = self.session.role or ""

        # Historical company average (low scores → probe deeper)
        avg_scores = insights.get("avg_scores_by_company") or {}
        company_avg = avg_scores.get(company)
        if isinstance(company_avg, (int, float)) and company_avg < 80:
            parts.append(
                f"Target company '{company}' historical interview average is {company_avg}; "
                "consider probing projects and technical depth a bit harder."
            )

        # Recent effective probe clues, prefer same company/role
        probes = insights.get("recent_probes") or []
        relevant: list[str] = []
        for p in probes:
            if not isinstance(p, dict):
                continue
            p_company = p.get("company") or ""
            p_role = p.get("role") or ""
            # Prefer same company or role; otherwise take generic clues
            if p_company == company or p_role == role or not relevant:
                relevant.append(str(p.get("point", ""))[:120])
            if len(relevant) >= 3:
                break
        if relevant:
            parts.append(
                "Common weak spots from recent interviews (probe if relevant):\n- "
                + "\n- ".join(relevant)
            )

        if not parts:
            return ""
        return "\n\n## System learning summary (cross-interview; for reference)\n" + "\n".join(parts)

    def _memory_section(self) -> str:
        """Structured memory summary (still usable after compression)."""
        text = WorkingMemory.from_state(self.agent_state).render()
        cognitive_graph = getattr(self, "cognitive_memory", None)
        if cognitive_graph is not None:
            cog_text = cognitive_graph.render_prompt_summary()
            if cog_text:
                text = (text + "\n\n" + cog_text).strip()
        if not text:
            return ""
        return f"\n\n{_MEMORY_SECTION_MARKER}\n" + text

    def _score_section(self) -> str:
        """Render the per-question score trajectory (empty when no scores yet).

        Turn scores otherwise survive only as ``last_turn_score`` (one entry,
        overwritten each turn); this gives the summary/verdict turns a
        calibrated view of the whole session.
        """
        scores = self.agent_state.get("turn_scores") or []
        lines: list[str] = []
        for i, s in enumerate(scores[-20:], start=1):
            if not isinstance(s, dict):
                continue
            rating = s.get("rating") or 0
            brief = str(s.get("brief") or "").strip()
            weak = "; ".join(str(w) for w in (s.get("weak_points") or [])[:2])
            line = f"{i}. {rating}/5" + (f" — {brief}" if brief else "")
            if weak:
                line += f" (weak: {weak})"
            lines.append(line)
        if not lines:
            return ""
        return (
            "\n\n## Per-question score trajectory (rating 1-5, this round)\n"
            + "\n".join(lines)
        )

    def _flow_view(self) -> Any:
        """Workflow-like object for prompt assembly: plan steps when planned."""
        plan = getattr(self, "plan", None)
        if plan is not None:
            name = plan.round_note or "Agent-planned interview flow"
            return Workflow(id="planned", name=name, phases=list(plan.steps))
        return self.workflow

    def _plan_is_agent_authored(self) -> bool:
        plan = getattr(self, "plan", None)
        return plan is not None and plan.source == "agent"

    def _round_identity_section(self, step) -> str:
        """Interviewer identity + focus line for this round of a process chain.

        ``step`` is a :class:`RoundStep` from the realistic chain, so each
        round reads as a DIFFERENT interviewer (technical expert vs HR) with
        its own focus instead of the same interviewer repeated.
        """
        if step is None:
            return ""
        return (
            f"\n\n## This round: {step.label} (round {step.round_no})\n"
            f"Interviewer persona this round: {step.personality} style, "
            f"interview_style={step.interview_style}, strictness={step.strictness}/10. "
            "You ARE this interviewer; do not mention other rounds' interviewers.\n"
            f"This round focus: {step.focus}."
        )

    def _process_round_section(self) -> str:
        """Cross-round memory + round identity for multi-round processes."""
        process_id = getattr(self.session, "process_id", None)
        if not process_id:
            return ""
        try:
            with sessions_db_session() as db:
                process = (
                    db.query(InterviewProcess)
                    .filter(InterviewProcess.id == process_id)
                    .first()
                )
                if process is None:
                    return ""
                rendered = render_for_prompt(load_memory(process.memory))
                step = step_for(
                    process.workflow_type,
                    getattr(self.session, "round_no", 1) or 1,
                    process.max_rounds,
                )
        except Exception:
            logger.warning("process memory read failed pid=%s", process_id, exc_info=True)
            return ""
        identity = self._round_identity_section(step)
        if not rendered:
            return identity
        return (
            f"\n\n## Prior rounds memory (this process; round "
            f"{getattr(self.session, 'round_no', '?')} of max {process.max_rounds})\n"
            f"{rendered}\n"
            "Handover: you have READ the earlier rounds' feedback above — like a "
            "real interviewer who reviewed notes before the call. Open with one "
            "natural line that shows it (mention the candidate's stated focus or "
            "one concrete claim from a previous round), then interview from there. "
            "Never re-ask a covered question: a repeat is allowed only as a harder "
            "variant or a genuinely new angle. Start this round's probing from the "
            "weak points listed above, and calibrate difficulty to this round's "
            "position in the loop."
        ) + identity

    def _flow_language(self) -> str:
        """Working language decided by the flow planner ("en" or "zh")."""
        plan = getattr(self, "plan", None)
        if plan is not None and getattr(plan, "source", "") == "agent":
            return getattr(plan, "language", "zh") or "zh"
        return "zh"

    def _opening_section(self) -> str:
        """Opening-style directive from the flow plan (randomized per session)."""
        plan = getattr(self, "plan", None)
        opening = getattr(plan, "opening", None) if plan is not None else None
        style = getattr(opening, "style", "") or "identity_confirm"
        note = getattr(opening, "note", "") or ""
        guides = {
            "identity_confirm": (
                "Confirm identity briefly (candidate name + applied role), one short "
                "exchange, then move into the first topic. Do not interrogate."
            ),
            "resume_ack": (
                "State that you have read the resume, recap the candidate by name plus "
                "one concrete resume fact, confirm everything is OK, and go straight "
                "into the opening topic. Skip any identity interrogation."
            ),
            "casual_warmup": (
                "Open with at most two sentences of warm small talk (greeting, audio "
                "check), then start the interview."
            ),
        }
        guide = guides.get(style, guides["identity_confirm"])
        section = f"\n\n## Opening style for this session: {style}\n{guide}"
        if note:
            section += f"\nPersonalization (use these facts): {note}"
        return section

    def build_opening_prompt(self, db: Session) -> str:
        """Build the opening-turn system prompt."""
        config = self.get_config()
        candidate = self.get_candidate(db)
        profile = self.get_user_profile(db)
        # Custom companies carry a web-research digest (planning stage) that
        # replaces the generic catalog line; preset companies keep the catalog.
        company_ctx = blend_company_context(
            get_company_context(config.company),
            load_session_company_research(db, self.session),
        )
        phase = self.current_phase()
        prompt = build_system_prompt(
            config,
            candidate,
            company_ctx,
            self._flow_view(),
            phase,
            profile,
            allow_plan_ops=self._plan_is_agent_authored(),
            flow_language=self._flow_language(),
        )
        # System learning (stable for the session) + prior rounds + structured memory (refreshed each turn)
        full = (
            prompt
            + self._opening_section()
            + self._system_learning_section()
            + self._process_round_section()
            + self._memory_section()
        )
        try:
            from realmock.platform.capabilities.ai.context.estimation import estimate_messages_tokens

            system_tokens = estimate_messages_tokens([{"role": "system", "content": full}])
        except Exception:
            system_tokens = -1
        logger.debug(
            "opening system prompt sid=%s tokens~%s lang=%s",
            getattr(self.session, "id", None), system_tokens, self._flow_language(),
        )
        return full

    @staticmethod
    def _strip_memory_section(content: str) -> str:
        """Drop the trailing structured-memory section (and blank lines before it)."""
        for marker in (
            _MEMORY_SECTION_MARKER,
            "## Conversation structured memory (do not repeat questions that have been asked)",
        ):
            if marker in content:
                return content.split(marker)[0].rstrip()
        return content.rstrip()

    def refresh_system_memory(self) -> None:
        """Refresh the structured-memory section in the system prompt head.

        Called each turn so asked_questions / weak_points / github_findings stay
        current after long-context compression, avoiding repeat questions and
        lost weak-spot tracking.

        Only replaces the memory section inside ``messages[0]`` system content;
        does not rebuild the whole prompt (avoids re-querying profile/company).
        """
        if not self.messages or self.messages[0].get("role") != "system":
            return
        content = self.messages[0].get("content", "")
        if not isinstance(content, str):
            return
        content = self._strip_memory_section(content)
        memory = self._memory_section()
        if memory:
            self.messages[0]["content"] = content + "\n\n" + memory

    def refresh_system_head(self, phase, *, profile=None, candidate=None) -> None:
        """Rebuild the phase-dependent sections of ``messages[0]`` on phase advance.

        The opening system prompt freezes two sections that go stale as the
        flow moves: the candidate block (rendered full for questioning phases)
        and the ``## Current phase`` lines. Entering a phase that asks no
        resume questions (reverse_qa / summary) swaps the block for the
        compact identity card; every entry refreshes the phase lines so the
        head no longer points at the opening phase.

        ``profile`` / ``candidate`` are injected for tests; when omitted the
        candidate rows are re-read (phase advances are rare, so one extra
        lookup is fine). Unknown prompt shapes leave the head untouched.
        """
        if not self.messages or self.messages[0].get("role") != "system":
            return
        content = self.messages[0].get("content", "")
        if not isinstance(content, str):
            return
        core = self._strip_memory_section(content)
        phase_idx = core.find("## Current phase")
        if phase_idx < 0:
            return
        head = core[:phase_idx]
        tail = core[phase_idx:]
        flow_idx = tail.find("## Full flow")
        flow_tail = tail[flow_idx:] if flow_idx >= 0 else ""

        needs_compact = needs_compact_candidate(phase)
        is_currently_compact = "## Candidate (compact" in core
        middle = ""
        if needs_compact or is_currently_compact:
            # Only strip the candidate block when we are about to replace it.
            # Normal questioning-phase advances keep the full block and only
            # refresh the phase lines below.
            start = -1
            for marker in ("## Candidate profile", "## Parsed resume", "## Candidate (compact"):
                idx = head.find(marker)
                if idx >= 0 and (start < 0 or idx < start):
                    start = idx
            if start >= 0:
                head = head[:start]
            if profile is None:
                with api_db_session() as api_db:
                    profile = get_user_profile(api_db, self.session.profile_id)
            if candidate is None:
                with api_db_session() as api_db:
                    candidate = get_candidate_profile(api_db, self.session.resume_id)
            if needs_compact:
                middle = compact_candidate_block(profile, candidate) + "\n"
            else:
                # Leaving a compact-only phase (reverse_qa/summary) for a
                # questioning phase: restore the full candidate block so the
                # model keeps resume grounding for the rest of the interview.
                # With no profile/resume data the full block renders empty —
                # keep the compact identity card rather than dropping the
                # section entirely.
                restored = candidate_block(profile, candidate, compact=False)
                middle = (restored or compact_candidate_block(profile, candidate)) + "\n"

        new_phase_block = (
            "## Current phase\n"
            f"Phase: {phase.name} ({phase.id})\n"
            f"Goal: {phase.description}\n"
            f"Ask {phase.min_questions}-{phase.max_questions} questions in this phase.\n\n"
        )
        updated = head + middle + new_phase_block + flow_tail
        memory = self._memory_section()
        if memory:
            updated += "\n\n" + memory
        self.messages[0]["content"] = updated


__all__ = ["SessionPromptMixin"]
