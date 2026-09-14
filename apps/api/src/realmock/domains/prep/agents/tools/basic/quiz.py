"""Quiz tool: pose a practice question for the candidate."""

from __future__ import annotations

from typing import Any

from realmock.domains.prep.agents.tools.spec import SearchHits, ToolSpec
from realmock.platform.capabilities.ai.agent import WorkingMemory


# Working-memory bound: unbounded quiz text would bloat every later turn's prompt.
_QUIZ_MAX_CHARS = 2000


async def run_quiz(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
    """Record the quiz in working memory; the formal question renders in the reply."""
    question = str(args.get("question", "") or "")[:_QUIZ_MAX_CHARS]
    qtype = str(args.get("type", "open") or "open")
    memory.remember("quiz", f"{qtype}:{question}")
    return (
        f"Quiz noted; present it in your formal reply and wait for the user: {question} ({qtype})",
        [],
    )


QUIZ_SPEC = ToolSpec(
    name="quiz",
    description="Give the candidate a practice question (multiple-choice or open).",
    parameters={
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "type": {
                "type": "string",
                "enum": ["choice", "open"],
                "description": "Question type",
            },
        },
        "required": ["question"],
    },
    handler=run_quiz,
)


__all__ = ["QUIZ_SPEC", "run_quiz"]
