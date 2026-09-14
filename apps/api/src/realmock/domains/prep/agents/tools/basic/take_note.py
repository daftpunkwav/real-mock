"""Take-note tool: persist turn conclusions into working memory."""

from __future__ import annotations

from typing import Any

from realmock.domains.prep.agents.tools.spec import SearchHits, ToolSpec
from realmock.platform.capabilities.ai.agent import WorkingMemory


# Working-memory bound: unbounded notes would bloat every later turn's prompt.
_TAKE_NOTE_MAX_CHARS = 2000


async def run_take_note(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
    """Write weak spots / decisions into working memory for later turns.

    Args:
        args: Tool arguments (``kind`` note/weak_point, ``content`` up to
            2000 chars; empty content records nothing).
        memory: Working memory receiving the note.

    Returns:
        ``(acknowledgement_text, [])``.
    """
    kind = str(args.get("kind", "note") or "note")
    content = str(args.get("content", "") or "").strip()[:_TAKE_NOTE_MAX_CHARS]
    if not content:
        return "take_note missing content; nothing recorded.", []
    memory.remember("weak" if kind == "weak_point" else "note", content)
    return f"Saved to working memory ({kind}): {content}", []


TAKE_NOTE_SPEC = ToolSpec(
    name="take_note",
    description=(
        "Write a note into session working memory (visible in later turns): "
        "user weak spots, confirmed target role/company, or key conclusions."
    ),
    parameters={
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "enum": ["note", "weak_point"],
                "description": "note=general point, weak_point=user weak spot",
            },
            "content": {"type": "string"},
        },
        "required": ["kind", "content"],
    },
    handler=run_take_note,
)


__all__ = ["TAKE_NOTE_SPEC", "run_take_note"]
