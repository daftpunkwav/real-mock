"""Session prompt builder mixin: profile lookup, company context, structured memory.

Split from :class:`realmock.domains.interview.services.interview.session_state.InterviewSessionState`.
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
from realmock.domains.interview.services.interview.agent_prompts import build_system_prompt
from realmock.domains.interview.services.interview.workflows import Workflow
from realmock.domains.interview.services.process_memory import load_memory, render_for_prompt
from realmock.domains.interview.services.round_chain import step_for

if TYPE_CHECKING:
    from realmock.domains.interview.services.interview.session_state import InterviewSessionState

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
        with api_db_session() as api_db:
            return get_user_profile(api_db, self.session.profile_id)

    def get_candidate(self, db: Session):
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
        if not text:
            return ""
        return f"\n\n{_MEMORY_SECTION_MARKER}\n" + text

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
            "Hand over like a real loop: greet briefly as a NEW interviewer, do not "
            "repeat what already went well, probe the weak points above from new "
            "angles, and calibrate difficulty for this round."
        ) + identity

    def build_opening_prompt(self, db: Session) -> str:
        """Build the opening-turn system prompt."""
        config = self.get_config()
        candidate = self.get_candidate(db)
        profile = self.get_user_profile(db)
        company_ctx = get_company_context(config.company)
        phase = self.current_phase()
        prompt = build_system_prompt(
            config,
            candidate,
            company_ctx,
            self._flow_view(),
            phase,
            profile,
            allow_plan_ops=self._plan_is_agent_authored(),
        )
        # System learning (stable for the session) + prior rounds + structured memory (refreshed each turn)
        return (
            prompt
            + self._system_learning_section()
            + self._process_round_section()
            + self._memory_section()
        )

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
        # Drop the old memory section (and blank lines before it), then append fresh
        # Also strip the legacy Chinese marker so mid-session upgrades still refresh.
        for marker in (
            _MEMORY_SECTION_MARKER,
            "## Conversation structured memory (do not repeat questions that have been asked)",
        ):
            if marker in content:
                content = content.split(marker)[0].rstrip()
                break
        memory = self._memory_section()
        if memory:
            self.messages[0]["content"] = content + "\n\n" + memory


__all__ = ["SessionPromptMixin"]
