"""Shadow Evaluator Agent for rigorous technical assessment and probing suggestions.

Responsibilities:
- Inspect candidate answers for technical depth, logical consistency, and buzzword avoidance.
- Detect discrepancies with previously claimed knowledge or system limits.
- Formulate high-value whispering directives for the Lead Interviewer.
- Feed structured evaluations directly into the CognitiveMemoryGraph.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from realmock.domains.interview.agents.memory.cognitive_graph import (
    CognitiveMemoryGraph,
    CompetencyStatus,
)
from realmock.platform.capabilities.ai.llm.client import LLMClient

logger = logging.getLogger(__name__)

SHADOW_SYSTEM_PROMPT = """You are a senior principal engineer serving as the Shadow Technical Evaluator in an interview.
You listen to the candidate's response to identify:
1. Genuine engineering substance vs. superficial buzzwords.
2. Logical contradictions with prior statements or known architectural facts.
3. Specific blind spots or ambiguous claims that require immediate probing.
4. Whether the discussion has reached a point where asking the candidate to write code is optimal.

Format your response strictly as JSON:
{
  "substance_score": 7, // 1 to 10
  "is_consistent": true,
  "inconsistencies": ["any contradiction detected"],
  "technical_holes": ["missing detail, e.g. didn't explain failure modes"],
  "suggested_probe": "one sharp, targeted follow-up question for the lead interviewer",
  "should_trigger_coding": false,
  "assessed_topic": "specific topic name, e.g. Distributed Lock / Raft / Virtual DOM",
  "topic_status": "verified | suspicious | failed"
}
"""


@dataclass
class ShadowEvaluation:
    """Evaluation result produced by the Shadow Evaluator Agent."""
    substance_score: int = 5
    is_consistent: bool = True
    inconsistencies: list[str] = field(default_factory=list)
    technical_holes: list[str] = field(default_factory=list)
    suggested_probe: str = ""
    should_trigger_coding: bool = False
    assessed_topic: str = ""
    topic_status: str = "untested"


class ShadowEvaluatorAgent:
    """Background evaluation agent that operates alongside the Lead Interviewer."""

    def __init__(self, llm: LLMClient, memory_graph: CognitiveMemoryGraph) -> None:
        self.llm = llm
        self.memory_graph = memory_graph

    async def evaluate_turn(
        self,
        *,
        question: str,
        user_text: str,
        current_phase: str,
        turn_index: int,
    ) -> ShadowEvaluation:
        """Analyze a candidate's answer and produce deep technical evaluations."""
        if not user_text.strip() or not self.llm.api_key:
            return ShadowEvaluation()

        prompt_context = self.memory_graph.render_prompt_summary()
        user_message = (
            f"Interview Phase: {current_phase}\n"
            f"Question Asked: {question}\n"
            f"Candidate Answer: {user_text}\n"
            f"Current Assessment Context:\n{prompt_context}"
        )

        try:
            raw = await self.llm.chat_json(
                [
                    {"role": "system", "content": SHADOW_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.2,
            )
            if not raw or not isinstance(raw, dict):
                return ShadowEvaluation()

            try:
                substance_score = int(raw.get("substance_score", 5))
            except (ValueError, TypeError):
                substance_score = 5
            substance_score = max(1, min(10, substance_score))

            inconsistencies = [str(x) for x in raw.get("inconsistencies", []) if isinstance(x, (str, int, float))]
            technical_holes = [str(x) for x in raw.get("technical_holes", []) if isinstance(x, (str, int, float))]

            eval_res = ShadowEvaluation(
                substance_score=substance_score,
                is_consistent=bool(raw.get("is_consistent", True)),
                inconsistencies=inconsistencies,
                technical_holes=technical_holes,
                suggested_probe=str(raw.get("suggested_probe", "")).strip(),
                should_trigger_coding=bool(raw.get("should_trigger_coding", False)),
                assessed_topic=str(raw.get("assessed_topic", "")).strip(),
                topic_status=str(raw.get("topic_status", "untested")).lower(),
            )

            # Integrate finding into CognitiveMemoryGraph
            if eval_res.assessed_topic:
                status = (
                    CompetencyStatus(eval_res.topic_status)
                    if eval_res.topic_status in {s.value for s in CompetencyStatus}
                    else CompetencyStatus.UNTESTED
                )
                finding_detail = (
                    "; ".join(eval_res.technical_holes)
                    if eval_res.technical_holes
                    else f"Score {eval_res.substance_score}/10"
                )
                self.memory_graph.record_finding(
                    topic=eval_res.assessed_topic,
                    category=current_phase,
                    status=status,
                    claim=user_text[:200],
                    finding=finding_detail,
                    turn_index=turn_index,
                    confidence=eval_res.substance_score / 10.0,
                )

            if eval_res.suggested_probe:
                self.memory_graph.working_memory.pending_probes.append(eval_res.suggested_probe)
                self.memory_graph.working_memory.pending_probes = (
                    self.memory_graph.working_memory.pending_probes[-4:]
                )

            return eval_res
        except Exception as e:
            logger.warning("ShadowEvaluator turn analysis failed: %s", e)
            return ShadowEvaluation()
