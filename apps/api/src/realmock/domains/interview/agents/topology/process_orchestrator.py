"""Process Orchestrator Agent responsible for agenda management, dynamic pacing, and debrief synthesis.

Responsibilities:
- Monitor interview progression against the cognitive memory graph and time budget.
- Determine strategic transitions: deepening technical probes, initiating live coding, or advancing phases.
- Synthesize holistic candidate evaluation verdicts and structured debrief reports.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from realmock.domains.interview.agents.memory.cognitive_graph import (
    CognitiveMemoryGraph,
    CompetencyStatus,
)
from realmock.platform.capabilities.ai.llm.client import LLMClient

logger = logging.getLogger(__name__)


class OrchestrationDirective(str, Enum):
    """Macro directive issued by the Process Orchestrator to the Lead Interviewer."""
    CONTINUE = "continue"
    DEEPEN_PROBE = "deepen_probe"
    TRIGGER_CODING = "trigger_coding"
    ADVANCE_PHASE = "advance_phase"
    CONCLUDE_INTERVIEW = "conclude_interview"


@dataclass
class OrchestratorAdvice:
    directive: OrchestrationDirective = OrchestrationDirective.CONTINUE
    reason: str = ""
    target_topic: str = ""
    pacing_guidance: str = ""


ORCHESTRATOR_ADVICE_PROMPT = """You are the Lead HR & Technical Process Orchestrator in an executive technical interview.
Review the current candidate competency profile, elapsed turns, and current phase.

Directives available:
- continue: Keep exploring current sub-topic naturally.
- deepen_probe: Candidate gave ambiguous/suspicious answers on a critical area; instruct lead interviewer to dig in.
- trigger_coding: Candidate has articulated theoretical concepts; time to challenge them with a live coding problem.
- advance_phase: Current phase competencies are sufficiently established or exhausted; move to next phase.
- conclude_interview: We have gathered comprehensive evidence across all domains or time is up; wrap up.

Return ONLY valid JSON:
{
  "directive": "continue | deepen_probe | trigger_coding | advance_phase | conclude_interview",
  "reason": "Brief justification for this transition",
  "target_topic": "Topic to focus on if probing or advancing",
  "pacing_guidance": "Brief instruction on tone, pacing, or time urgency"
}
"""


class ProcessOrchestratorAgent:
    """Agent overseeing interview strategy, pacing, and macro-transitions."""

    def __init__(self, llm: LLMClient, memory_graph: CognitiveMemoryGraph) -> None:
        self.llm = llm
        self.memory_graph = memory_graph

    async def decide_next_step(
        self,
        *,
        current_phase: str,
        turn_index: int,
        elapsed_minutes: float,
        target_duration_minutes: float = 40.0,
    ) -> OrchestratorAdvice:
        """Evaluate interview progress and advise on macro-level pacing and phase transitions."""
        # Safety/time guards
        if elapsed_minutes >= target_duration_minutes - 5.0 and current_phase not in {"summary", "reverse_qa"}:
            return OrchestratorAdvice(
                directive=OrchestrationDirective.ADVANCE_PHASE,
                reason="Approaching time budget limit; wrap technical questions and move towards summary.",
                pacing_guidance="Strict pacing: begin wrapping up current topic.",
            )

        if not self.llm.api_key:
            return OrchestratorAdvice(
                directive=OrchestrationDirective.CONTINUE,
                reason="Standard flow progression.",
            )

        memory_summary = self.memory_graph.render_prompt_summary()
        user_msg = (
            f"Current Phase: {current_phase}\n"
            f"Turns Completed: {turn_index}\n"
            f"Elapsed Time: {elapsed_minutes:.1f} / {target_duration_minutes:.1f} minutes\n"
            f"Assessment Evidence:\n{memory_summary}"
        )

        try:
            raw = await self.llm.chat_json(
                [
                    {"role": "system", "content": ORCHESTRATOR_ADVICE_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.2,
            )
            if not raw or not isinstance(raw, dict):
                return OrchestratorAdvice()

            dir_str = str(raw.get("directive", "continue")).lower()
            directive = (
                OrchestrationDirective(dir_str)
                if dir_str in {d.value for d in OrchestrationDirective}
                else OrchestrationDirective.CONTINUE
            )

            return OrchestratorAdvice(
                directive=directive,
                reason=str(raw.get("reason", "")),
                target_topic=str(raw.get("target_topic", "")),
                pacing_guidance=str(raw.get("pacing_guidance", "")),
            )
        except Exception as e:
            logger.warning("ProcessOrchestrator decision failed: %s", e)
            return OrchestratorAdvice()
