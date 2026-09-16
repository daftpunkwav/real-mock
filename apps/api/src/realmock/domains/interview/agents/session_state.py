"""Interview session state machine (InterviewSessionState).

Responsibilities:
- Load and persist message history / phase index / structured state (agent_state);
- Advance phases and persist turn-control information;
- For system prompt construction, see :mod:`session_prompt` (SessionPromptMixin).

For prompts, see :mod:`agent_prompts`; for text filtering, see :mod:`agent_text`; for reports, see :mod:`report`.
Company catalog: cross-session company knowledge comes from :mod:`realmock.platform.catalogs.company`; this module only reads it.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from realmock.domains.interview.models import InterviewSession
from realmock.platform.catalogs.company import get_company_context
from realmock.domains.interview.agents.session_prompt import SessionPromptMixin
from realmock.domains.interview.agents.turn_output import TurnOutput
from realmock.domains.interview.agents.agent_text import (
    PHASE_COMPLETE_MARKER,
    has_marker,
    strip_markers,
)
from realmock.domains.interview.agents.memory.cognitive_graph import CognitiveMemoryGraph
from realmock.domains.interview.agents.workflows import Workflow, get_workflow
from realmock.domains.interview.process.planning.plan_schema import (
    MAX_PLAN_STEPS,
    REVERSE_QA_KIND,
    InterviewPlan,
    PlanStep,
    parse_plan,
)
from realmock.platform.capabilities.ai.llm.client import LLMClient

logger = logging.getLogger(__name__)


#: Interview-age marks (minutes) that trigger a one-shot pacing hint.
_PACE_THRESHOLDS = (30, 45, 60)


def _is_summary_phase(phase: Any) -> bool:
    """Whether this flow step is the wrap-up/verdict step."""
    for value in (getattr(phase, "id", ""), getattr(phase, "kind", "")):
        if "summary" in str(value or "").lower():
            return True
    return False


class InterviewSessionState(SessionPromptMixin):
    """Interview conversation state machine: message history, stage index, state persistence, prompt word construction.

    Flow source: an agent-planned :class:`InterviewPlan` when present on the
    session row, otherwise the static ``Workflow``. Both drive the same phase
    machinery (plan steps duck-type ``PhaseDef``).
    """

    def __init__(
        self,
        session: InterviewSession,
        llm: LLMClient,
        voice_directive: str | None = None,
    ):
        self.session = session
        self.llm = llm
        # Speech-synthesis channel notes (e.g. MiniMax interjection-tag support) baked
        # into the system prompt; None/"" renders nothing.
        self.voice_directive = (voice_directive or "").strip()
        self._load_state()

    # ---- State Loading/Saving -----------------------------------------------------

    def _load_state(self) -> None:
        try:
            self.agent_state: dict[str, Any] = json.loads(self.session.agent_state or "{}")
        except json.JSONDecodeError:
            logger.debug("corrupt agent_state JSON sid=%s; start fresh", getattr(self.session, "id", None))
            self.agent_state = {}

        try:
            self.messages: list[dict[str, Any]] = json.loads(self.session.messages or "[]")
        except json.JSONDecodeError:
            logger.debug("corrupt messages JSON sid=%s; start fresh", getattr(self.session, "id", None))
            self.messages = []

        self.workflow: Workflow = get_workflow(self.session.workflow_type)
        self.plan: InterviewPlan | None = self._load_plan()
        self.phases: list[Any] = self.plan.steps if self.plan else list(self.workflow.phases)
        # Clamp to the legal range to prevent obsolete or truncated workflows from crossing the boundary
        _raw_idx = self.agent_state.get("phase_idx", 0)
        _max_idx = max(0, len(self.phases) - 1)
        self.current_phase_idx: int = max(0, min(_raw_idx, _max_idx))
        self.questions_in_phase: int = self.agent_state.get("questions_in_phase", 0)
        self.asked_topics: list[str] = self.agent_state.get("asked_topics", [])
        # Long context structured memory (for 40-minute interview)
        self.agent_state.setdefault("weak_points", [])
        self.agent_state.setdefault("followup_clues", [])
        self.agent_state.setdefault("github_findings", [])
        self.agent_state.setdefault("tool_trace", [])
        self.agent_state.setdefault("asked_questions", [])
        self.cognitive_memory: CognitiveMemoryGraph = CognitiveMemoryGraph.from_dict(
            self.agent_state.get("cognitive_memory")
        )

    def _load_plan(self) -> InterviewPlan | None:
        try:
            return parse_plan(getattr(self.session, "plan", None))
        except Exception:
            logger.warning("plan parse failed sid=%s; using static workflow", getattr(self.session, "id", None))
            return None

    def reload_plan(self) -> None:
        """Re-read the plan from the session row (after background planning)."""
        self.plan = self._load_plan()
        self.phases = self.plan.steps if self.plan else list(self.workflow.phases)
        self.current_phase_idx = max(0, min(self.current_phase_idx, len(self.phases) - 1))

    def save_state(self, db: Session) -> None:
        """Write the current state back to the database."""
        self.agent_state.update({
            "phase_idx": self.current_phase_idx,
            "questions_in_phase": self.questions_in_phase,
            "asked_topics": self.asked_topics,
            "cognitive_memory": self.cognitive_memory.to_dict(),
        })
        self.session.agent_state = json.dumps(self.agent_state, ensure_ascii=False)
        self.session.messages = json.dumps(self.messages, ensure_ascii=False)
        self.session.current_phase = self.current_phase().id
        if self.plan is not None:
            # Persist plan mutations from plan_ops (step insertions).
            self.session.plan = json.dumps(self.plan.to_dict(), ensure_ascii=False)
        db.commit()

    def note_question(self, question_text: str) -> None:
        """Record the questions that have been asked (structured to facilitate deduplication after compression)."""
        q = (question_text or "").strip()
        if not q:
            return
        asked = self.agent_state.setdefault("asked_questions", [])
        # Keep first 120 chars
        snippet = q[:120]
        if snippet not in asked:
            asked.append(snippet)
        if len(asked) > 80:
            del asked[:-80]

    def note_weak_point(self, point: str) -> None:
        """Record clues about candidate weaknesses."""
        p = (point or "").strip()
        if not p:
            return
        weak = self.agent_state.setdefault("weak_points", [])
        if p not in weak:
            weak.append(p[:200])
        if len(weak) > 30:
            del weak[:-30]

    def note_turn_output(self, output: TurnOutput) -> None:
        """Persistent round control information: questioning plan and real-time brief review (realistic questioning/report reuse)."""
        if output.probe:
            self.agent_state["last_probe"] = output.probe
        ts = output.turn_score
        if ts:
            self.agent_state["last_turn_score"] = {
                "brief": ts.brief,
                "rating": ts.rating,
                "weak_points": list(ts.weak_points),
            }
            # Full per-question trajectory: feeds the summary/verdict prompt
            # and the ledger turn flags (last_turn_score alone gets overwritten).
            scores = self.agent_state.setdefault("turn_scores", [])
            scores.append({
                "brief": ts.brief,
                "rating": ts.rating,
                "weak_points": list(ts.weak_points),
            })
            if len(scores) > 40:
                del scores[:-40]
            for p in ts.weak_points:
                self.note_weak_point(p)

    def note_verdict(self, verdict: str | None) -> None:
        """Persist the agent-announced round verdict onto the session row."""
        if verdict not in ("passed", "failed"):
            return
        self.session.result = verdict

    def pace_message(self) -> str | None:
        """One-shot pacing system message when the interview crosses a time mark.

        The flow has a question budget but no sense of wall-clock time, so a
        talkative candidate can silently overrun. Fires once per threshold
        (30/45/60 min, tracked in agent_state) and returns None otherwise.
        """
        started = getattr(self.session, "started_at", None)
        if started is None:
            return None
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        minutes = int((datetime.now(timezone.utc) - started).total_seconds() // 60)
        marks = self.agent_state.setdefault("pace_marks", [])
        for threshold in _PACE_THRESHOLDS:
            if minutes >= threshold and threshold not in marks:
                marks.append(threshold)
                return (
                    f"[Pace: the interview has been running about {minutes} minutes. "
                    "Tighten probes, skip what is already demonstrated, and steer "
                    "toward the summary phase once this phase's material is covered.]"
                )
        return None

    # ---- Phase Queries -----------------------------------------------------------

    def current_phase(self) -> Any:
        """Current flow step: an agent PlanStep or a static PhaseDef."""
        if self.current_phase_idx < len(self.phases):
            return self.phases[self.current_phase_idx]
        return self.phases[-1]

    def phases_remaining(self) -> list[str]:
        """Display names of the current and all later phases/steps."""
        return [p.name for p in self.phases[self.current_phase_idx:]]

    def phase_title_for_display(self) -> str:
        """Agent-authored step title for WS events; empty for the static flow
        (static phase ids are localized client-side via i18n)."""
        if self._plan_is_agent_authored():
            return self.current_phase().name
        return ""

    def apply_plan_ops(self, plan_ops: tuple[dict, ...]) -> int:
        """Insert model-requested steps after the current one (plan mode only).

        Returns the number of steps inserted. The total step cap is enforced.
        """
        if not plan_ops or self.plan is None:
            return 0
        inserted = 0
        for raw in plan_ops:
            if len(self.plan.steps) >= MAX_PLAN_STEPS:
                break
            step = PlanStep(
                id=f"s{len(self.plan.steps) + 1:02d}",
                title=str(raw.get("title") or "").strip()[:60],
                focus=str(raw.get("focus") or "").strip()[:400],
                min_questions=1,
                max_questions=max(1, min(int(raw.get("max_questions") or 3), 8)),
                kind=str(raw.get("kind") or "").strip()[:30],
            )
            if not step.title:
                continue
            self.plan.steps.insert(self.current_phase_idx + 1 + inserted, step)
            inserted += 1
        if inserted:
            logger.info(
                "plan_ops inserted %d step(s) sid=%s", inserted, getattr(self.session, "id", None)
            )
        return inserted

    # ---- State Progression ----------------------------------------------------------

    def mark_active(self) -> None:
        """Mark the session as ongoing."""
        self.session.status = "active"
        self.session.started_at = datetime.now(timezone.utc)

    def mark_completed(self) -> None:
        """Mark the end of the interview and point the stage index to the end."""
        self.session.status = "completed"
        self.session.ended_at = datetime.now(timezone.utc)
        self.current_phase_idx = len(self.phases) - 1

    def record_user_text(self, content: str) -> None:
        """Record candidate speech into message history."""
        self.messages.append({"role": "user", "content": content})

    def record_assistant_text(self, content: str) -> None:
        """Record the interviewer's remarks into the message history and write structured questions that have been asked."""
        self.messages.append({"role": "assistant", "content": content})
        # Control tag stripped and credited to asked_questions
        clean = strip_markers(content)
        if clean:
            self.note_question(clean)

    def reset_messages(self) -> None:
        """Reset message history (when used on start)."""
        self.messages = []

    def set_questions_in_phase(self, value: int) -> None:
        """Reset the per-phase question counter (used on start)."""
        self.questions_in_phase = value

    def advance_phase_if_needed(
        self, reply: str, *, phase_complete: bool | None = None
    ) -> bool:
        """Decide whether to advance to the next phase based on the LLM response.

        ``phase_complete`` comes from the turn protocol's control section; when None, fall back
        to legacy marker detection (for compatibility with historical messages from before compaction).

        Returns:
            bool: Whether a phase transition occurred.
        """
        if phase_complete is None:
            phase_complete = has_marker(reply, PHASE_COMPLETE_MARKER)
        max_reached = self.questions_in_phase >= self.current_phase().max_questions
        if phase_complete or max_reached:
            # Defense: Avoid crossing the boundary and going beyond the end of the workflow
            if self.current_phase_idx >= len(self.phases) - 1:
                self.questions_in_phase += 1
                return False
            self._advance_phase()
            return True
        self.questions_in_phase += 1
        return False

    def _advance_phase(self) -> None:
        self.current_phase_idx += 1
        self.questions_in_phase = 0
        if self.current_phase_idx < len(self.phases):
            phase = self.current_phase()
            # Keep the frozen system head in sync: swap the candidate block
            # for the compact card on non-questioning phases and refresh the
            # stale "Current phase" lines (see SessionPromptMixin).
            self.refresh_system_head(phase)
            content = self._phase_entry_message(phase)
            self.messages.append({
                "role": "system",
                "content": content,
            })

    def _phase_entry_message(self, phase: Any) -> str:
        """Build the system message when entering a new phase.

        reverse_qa uses a dedicated company-representative prompt (answer from
        company knowledge; admit gaps honestly). Other phases use a generic cue.
        The summary phase carries the per-question score trajectory so the
        wrap-up verdict is grounded in the whole session, not just the tail.
        """
        if phase.id == "reverse_qa" or getattr(phase, "kind", "") == REVERSE_QA_KIND:
            company_ctx = get_company_context(self.session.company or "")
            return (
                f"Entering new phase: {phase.name} ({phase.description}).\n"
                f"{company_ctx}\n\n"
                "Role switch: you are no longer the examiner — you are a company "
                "representative (senior engineer / HR). Answer the candidate about "
                "culture, team, tech stack, business direction, and growth opportunities.\n"
                "Requirements:\n"
                "1. Answer from the company material above; if uncovered, honestly say "
                "\"I don't have exact information on that\"\n"
                "2. Be professional and grounded; avoid empty slogans\n"
                "3. You may still use web_search_interview_exp for public info\n"
                "4. Do not use emoji in replies"
            )
        message = (
            f"Entering new phase: {phase.name} ({phase.description}). "
            "Begin asking questions for this phase. Do not use emoji in replies."
        )
        if _is_summary_phase(phase):
            scores = self._score_section()
            if scores:
                message += (
                    scores
                    + "\nGround your wrap-up evaluation and the passed/failed verdict "
                    "in this trajectory, not just the last answer."
                )
        return message


__all__ = ["InterviewSessionState"]
