"""Shadow Evaluator Agent: rigorous background assessment in up to 3 LLM calls.

Pipeline (per answered turn, run in the background — never gates the reply):

1. evaluate: score substance, check consistency against the cognitive graph,
   list holes, name the assessed topic and its status;
2. recheck: only when phase 1 flags its own evidence as insufficient — the
   same material is re-examined with the doubts spelled out;
3. probe synthesis: only when no usable probe came out of 1/2 — one focused
   call distills the next whispering directive.

Rich context (resume/profile/company grounding, step focus, the graph's own
summary) is injected verbatim; the agent has no tools. Budget policy lives in
:mod:`agent_policies` (BACKGROUND.shadow_seconds bounds the whole pipeline).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from realmock.domains.interview.agents.memory.cognitive_graph import (
    CognitiveMemoryGraph,
    CompetencyStatus,
)
from realmock.domains.interview.agents.topology.prompts import (
    SHADOW_PROBE_PROMPT,
    SHADOW_RECHECK_PROMPT,
    SHADOW_SYSTEM_PROMPT,
)
from realmock.platform.capabilities.ai.llm.client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class ShadowEvaluation:
    """Evaluation result produced by the Shadow Evaluator Agent."""

    substance_score: int = 5
    is_consistent: bool = True
    inconsistencies: list[str] = field(default_factory=list)
    technical_holes: list[str] = field(default_factory=list)
    suggested_probe: str = ""
    assessed_topic: str = ""
    topic_status: str = "untested"
    # Phase-1 self flag: the answer does not carry enough evidence to judge
    # confidently — triggers the phase-2 recheck.
    evidence_insufficient: bool = False
    # Set when the pipeline could not evaluate at all (caller can tell this
    # apart from a genuinely mediocre answer).
    error: bool = False


def _clip(text: str, limit: int) -> str:
    return str(text or "").strip()[:limit]


class ShadowEvaluatorAgent:
    """Background evaluation agent that operates alongside the Lead Interviewer."""

    def __init__(
        self,
        llm: LLMClient,
        memory_graph: CognitiveMemoryGraph,
        context_provider: Callable[[], str] | None = None,
    ) -> None:
        self.llm = llm
        self.memory_graph = memory_graph
        self._context_provider = context_provider

    def _grounding(self) -> str:
        if self._context_provider is None:
            return ""
        try:
            return self._context_provider() or ""
        except Exception:
            logger.debug("shadow context provider failed", exc_info=True)
            return ""

    async def evaluate_turn(
        self,
        *,
        question: str,
        user_text: str,
        current_phase: str,
        turn_index: int,
        step_focus: str = "",
    ) -> ShadowEvaluation:
        """Analyze a candidate's answer and produce deep technical evaluations."""
        if not user_text.strip() or not self.llm.api_key:
            return ShadowEvaluation()

        eval_res = await self._evaluate(question, user_text, current_phase, step_focus)
        if eval_res is None:
            return ShadowEvaluation(error=True)
        # Phase 2 — self-declared insufficient evidence buys one recheck.
        if eval_res.evidence_insufficient:
            rechecked = await self._recheck(
                question, user_text, current_phase, step_focus, eval_res
            )
            if rechecked is not None:
                eval_res = rechecked
        # Phase 3 — no usable probe after 1/2: one focused synthesis call.
        if not eval_res.suggested_probe and eval_res.assessed_topic:
            probe = await self._synthesize_probe(question, user_text, eval_res)
            if probe:
                eval_res.suggested_probe = probe

        self._record(eval_res, user_text, current_phase, turn_index)
        return eval_res

    # ---- pipeline phases --------------------------------------------------

    async def _evaluate(
        self, question: str, user_text: str, current_phase: str, step_focus: str
    ) -> ShadowEvaluation | None:
        graph_summary = self.memory_graph.render_prompt_summary()
        grounding = self._grounding()
        user_message = (
            f"Interview step: {current_phase}"
            + (f"\nStep focus: {_clip(step_focus, 300)}" if step_focus else "")
            + f"\nQuestion asked: {_clip(question, 500)}\n"
            + (f"\n{grounding}\n" if grounding else "")
            + (f"\nCurrent assessment context:\n{graph_summary}" if graph_summary else "")
            + f"\n\nCandidate answer:\n{_clip(user_text, 6000)}"
        )
        try:
            raw = await self.llm.chat_json(
                [
                    {"role": "system", "content": SHADOW_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.2,
            )
        except Exception as e:
            logger.warning("ShadowEvaluator turn analysis failed: %s", e)
            return None
        return self._parse(raw)

    async def _recheck(
        self,
        question: str,
        user_text: str,
        current_phase: str,
        step_focus: str,
        prior: ShadowEvaluation,
    ) -> ShadowEvaluation | None:
        doubts = "; ".join(prior.technical_holes[:4]) or "insufficient evidence in the answer"
        user_message = (
            f"Interview step: {current_phase}"
            + (f"\nStep focus: {_clip(step_focus, 300)}" if step_focus else "")
            + f"\nQuestion asked: {_clip(question, 500)}\n"
            f"Your first pass flagged: {doubts}\n"
            "Re-examine with full attention to those doubts and give your final view.\n\n"
            f"Candidate answer:\n{_clip(user_text, 6000)}"
        )
        try:
            raw = await self.llm.chat_json(
                [
                    {"role": "system", "content": SHADOW_RECHECK_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.2,
            )
        except Exception as e:
            logger.debug("ShadowEvaluator recheck failed: %s", e)
            return None
        parsed = self._parse(raw)
        return parsed if parsed is not None else None

    async def _synthesize_probe(
        self, question: str, user_text: str, eval_res: ShadowEvaluation
    ) -> str:
        try:
            raw = await self.llm.chat_json(
                [
                    {"role": "system", "content": SHADOW_PROBE_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"Question: {_clip(question, 500)}\n"
                            f"Assessed topic: {eval_res.assessed_topic} "
                            f"({eval_res.topic_status}, score {eval_res.substance_score}/10)\n"
                            f"Holes: {'; '.join(eval_res.technical_holes[:3]) or 'none stated'}\n"
                            f"Candidate answer:\n{_clip(user_text, 3000)}"
                        ),
                    },
                ],
                temperature=0.4,
            )
        except Exception as e:
            logger.debug("ShadowEvaluator probe synthesis failed: %s", e)
            return ""
        if isinstance(raw, dict):
            return str(raw.get("probe") or "").strip()
        return ""

    # ---- parsing / persistence --------------------------------------------

    def _parse(self, raw: object) -> ShadowEvaluation | None:
        if not isinstance(raw, dict) or not raw:
            return None
        try:
            substance_score = int(raw.get("substance_score", 5))
        except (ValueError, TypeError):
            substance_score = 5
        substance_score = max(1, min(10, substance_score))
        return ShadowEvaluation(
            substance_score=substance_score,
            is_consistent=bool(raw.get("is_consistent", True)),
            inconsistencies=[
                str(x) for x in raw.get("inconsistencies", []) if isinstance(x, (str, int, float))
            ],
            technical_holes=[
                str(x) for x in raw.get("technical_holes", []) if isinstance(x, (str, int, float))
            ],
            suggested_probe=str(raw.get("suggested_probe", "")).strip(),
            assessed_topic=str(raw.get("assessed_topic", "")).strip(),
            topic_status=str(raw.get("topic_status", "untested")).lower(),
            evidence_insufficient=bool(raw.get("evidence_insufficient", False)),
        )

    def _record(
        self, res: ShadowEvaluation, user_text: str, current_phase: str, turn_index: int
    ) -> None:
        if not res.assessed_topic:
            return
        status = (
            CompetencyStatus(res.topic_status)
            if res.topic_status in {s.value for s in CompetencyStatus}
            else CompetencyStatus.UNTESTED
        )
        finding_detail = (
            "; ".join(res.technical_holes)
            if res.technical_holes
            else f"Score {res.substance_score}/10"
        )
        self.memory_graph.record_finding(
            topic=res.assessed_topic,
            category=current_phase,
            status=status,
            claim=_clip(user_text, 200),
            finding=finding_detail,
            turn_index=turn_index,
            confidence=res.substance_score / 10.0,
        )
        if res.suggested_probe:
            probes = self.memory_graph.working_memory.pending_probes
            probes.append(res.suggested_probe)
            self.memory_graph.working_memory.pending_probes = probes[-4:]
