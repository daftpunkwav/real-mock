"""
@file reflection.py
@description Periodic cognitive reflection and synthesis loop for interview memory.

Responsibilities:
- Periodically evaluate recent dialog turns to extract candidate claims vs. verified facts.
- Synthesize technical competence patterns and update the CognitiveMemoryGraph.
- Generate high-level debrief insights for downstream report generation.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from realmock.domains.interview.agents.memory.cognitive_graph import (
    CognitiveMemoryGraph,
    CompetencyStatus,
)
from realmock.platform.capabilities.ai.llm.client import LLMClient

logger = logging.getLogger(__name__)

REFLECTION_SYSTEM_PROMPT = """You are an expert technical interviewer and cognitive evaluator.
Analyze the recent interview turns and update the candidate's competency profile.

For each technical or architectural topic discussed:
1. Identify the candidate's core technical claims.
2. Determine if the claim was verified (solid rationale/tradeoffs), suspicious (vague/buzzword salad/inconsistent), or failed (incorrect/demonstrated lack of understanding).
3. Assign a confidence score (0.0 to 1.0).

Return ONLY valid JSON matching this schema:
{
  "reflections": [
    {
      "topic": "string (e.g. MySQL Indexing, Raft Consensus, React Rendering)",
      "category": "architecture | database | coding | fundamentals | system_design",
      "status": "verified | suspicious | failed",
      "claim": "brief summary of what candidate claimed",
      "finding": "technical assessment of why it was verified, suspicious, or failed",
      "confidence": 0.85
    }
  ],
  "suggested_next_probe": "one clear probe directive if any suspicious point requires digging"
}
"""


async def reflect_on_dialogue(
    llm: LLMClient,
    memory_graph: CognitiveMemoryGraph,
    recent_turns: list[dict[str, Any]],
    current_turn_index: int,
) -> None:
    """Perform async cognitive reflection on recent dialog turns and update the memory graph."""
    if not recent_turns or not llm.api_key:
        return

    turns_text = "\n".join(
        f"Turn {t.get('turn', i)}: [Interviewer]: {t.get('assistant', '')}\n[Candidate]: {t.get('user', '')}"
        for i, t in enumerate(recent_turns)
    )

    try:
        raw = await llm.chat_json(
            [
                {"role": "system", "content": REFLECTION_SYSTEM_PROMPT},
                {"role": "user", "content": f"Recent turns:\n{turns_text}"},
            ],
            temperature=0.2,
        )
        if not raw or not isinstance(raw, dict):
            return

        reflections = raw.get("reflections", [])
        if isinstance(reflections, list):
            for ref in reflections:
                if not isinstance(ref, dict):
                    continue
                topic = ref.get("topic")
                status_str = ref.get("status", "untested").lower()
                if not topic or status_str not in {s.value for s in CompetencyStatus}:
                    continue
                memory_graph.record_finding(
                    topic=topic,
                    category=ref.get("category", "general"),
                    status=CompetencyStatus(status_str),
                    claim=ref.get("claim", ""),
                    finding=ref.get("finding", ""),
                    turn_index=current_turn_index,
                    confidence=float(ref.get("confidence", 0.8)),
                )

        next_probe = raw.get("suggested_next_probe")
        if next_probe and isinstance(next_probe, str) and next_probe.strip():
            memory_graph.working_memory.pending_probes.append(next_probe.strip())
            # Keep at most 4 pending probes
            memory_graph.working_memory.pending_probes = memory_graph.working_memory.pending_probes[-4:]

        logger.info(
            "Reflection completed for turn=%d, updated_topics=%d",
            current_turn_index,
            len(reflections),
        )
    except Exception as e:
        logger.warning("Cognitive reflection failed gracefully: %s", e)
