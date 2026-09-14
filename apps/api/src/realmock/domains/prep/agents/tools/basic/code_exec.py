"""Code execution tool: verify algorithms via sandboxed snippets."""

from __future__ import annotations

import asyncio
from typing import Any

from realmock.domains.prep.agents.tools.spec import SearchHits, ToolSpec
from realmock.platform.capabilities.ai.agent import WorkingMemory
from realmock.platform.capabilities.ai.agent.tools import format_observation, run_code_snippet

# Sandbox wall-clock bound for LLM-requested snippets (platform truncates
# output; this clamp bounds worker-thread hold time per tool call).
_CODE_EXEC_DEFAULT_TIMEOUT = 10.0
_CODE_EXEC_MAX_TIMEOUT = 15.0


_CODE_MAX_CHARS = 20000


async def run_code_exec(args: dict[str, Any], memory: WorkingMemory) -> tuple[str, SearchHits]:
    """Run a short snippet in the sandbox.

    Args:
        args: Tool arguments (``language`` python/javascript, ``code``
            up to 20k chars, ``timeout`` seconds clamped 1..15).
        memory: Unused (no turn state to record).

    Returns:
        ``(observation_text, [])`` with stdout/stderr/exit code; empty code
        is refused without running.
    """
    del memory
    language = str(args.get("language", "") or "")
    code = str(args.get("code", "") or "")
    if not code.strip():
        return "code_exec missing code; nothing ran.", []
    code = code[:_CODE_MAX_CHARS]
    try:
        timeout = float(args.get("timeout", _CODE_EXEC_DEFAULT_TIMEOUT) or _CODE_EXEC_DEFAULT_TIMEOUT)
    except (TypeError, ValueError):
        timeout = _CODE_EXEC_DEFAULT_TIMEOUT
    timeout = min(max(timeout, 1.0), _CODE_EXEC_MAX_TIMEOUT)
    result = await asyncio.to_thread(run_code_snippet, language, code, timeout=timeout)
    return format_observation(result), []


CODE_EXEC_SPEC = ToolSpec(
    name="code_exec",
    description=(
        "Run a short Python or JavaScript snippet in a temp workspace and read "
        "its stdout/stderr/exit code. Use it to verify an algorithm, reproduce "
        "a bug, or check a computation before concluding — prefer running over "
        "guessing. Include prints for values to inspect; keep snippets small "
        "(~15s max, output truncated)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "language": {
                "type": "string",
                "enum": ["python", "javascript"],
                "description": "Snippet language",
            },
            "code": {
                "type": "string",
                "description": "Complete runnable snippet",
            },
            "timeout": {
                "type": "number",
                "description": "Seconds before kill (default 10, max 15)",
            },
        },
        "required": ["language", "code"],
    },
    handler=run_code_exec,
)


__all__ = ["CODE_EXEC_SPEC", "run_code_exec"]
