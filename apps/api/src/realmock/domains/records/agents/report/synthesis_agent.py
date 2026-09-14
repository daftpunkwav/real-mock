"""Stage 2: synthesis ReAct loop producing the report-level verdict and scores.

Reads the accumulated stage-1 notes through a paged tool (never one giant
prompt), spot-checks the ledger where notes look unsupported, and writes the
aligned verdict, score_breakdown, highlights / key problems, and plan.
"""

from __future__ import annotations

from typing import Any

from realmock.domains.records.agents.report.finalize import finalize_json
from realmock.domains.records.agents.report.ledger_tools import (
    ledger_tool_specs,
    notes_tool_specs,
)
from realmock.domains.records.agents.report.prompts import (
    SYNTHESIS_SYSTEM_PROMPT,
    report_json_schema_text,
    synthesis_user_message,
)
from realmock.platform.capabilities.ai.agent import OnAgentEvent as OnEvent
from realmock.platform.capabilities.ai.agent import emit_agent_event
from realmock.platform.capabilities.ai.agent.tools.spec import ToolBundle
from realmock.platform.capabilities.ai.agent.tools import invoke_with_timeout

SYNTHESIS_MAX_ROUNDS = 10
_TOOL_TIMEOUT_SECONDS = 30.0


async def run_synthesis(
    llm: Any,
    *,
    ledger: dict[str, Any],
    notes: list[dict[str, Any]],
    role: str,
    level: str,
    company: str,
    workflow_type: str,
    strictness: int,
    interview_style: str,
    session_result: str | None,
    process_context: str = "",
    context_specs: list[Any] | None = None,
    on_event: OnEvent | None = None,
) -> dict[str, Any] | None:
    """Run the synthesis loop; returns the raw report payload dict (or None)."""
    bundle = ToolBundle()
    bundle.extend(notes_tool_specs(notes))
    bundle.extend(ledger_tool_specs(ledger))
    if context_specs:
        bundle.extend(context_specs)

    async def execute(name: str, args: dict[str, Any]) -> str:
        raw, _status = await invoke_with_timeout(
            bundle, name, args, timeout=_TOOL_TIMEOUT_SECONDS
        )
        return raw

    async def on_tool(name: str, args: dict[str, Any], result: str, tc_id: str) -> None:
        del tc_id
        await emit_agent_event(on_event, {
            "type": "tool_step",
            "stage": "synthesis",
            "name": name,
            "args": {k: str(v)[:80] for k, v in (args or {}).items()},
            "status": "done",
            "result": str(result)[:400],
        })

    messages = [
        {"role": "system", "content": SYNTHESIS_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": synthesis_user_message(
                role=role,
                level=level,
                company=company,
                workflow_type=workflow_type,
                strictness=strictness,
                interview_style=interview_style,
                session_result=session_result,
                total_turns=len(notes),
                process_context=process_context,
            ),
        },
    ]

    async def on_thinking(text: str) -> None:
        if text.strip():
            await emit_agent_event(on_event, {"type": "thinking", "content": text[:600]})

    loop = await run_agent_loop_safe(
        llm, messages, bundle.definitions(), execute, on_tool, on_thinking
    )
    return await finalize_json(
        llm, loop, schema_text=report_json_schema_text(), purpose="report synthesis"
    )


async def run_agent_loop_safe(llm, messages, tools, execute, on_tool, on_thinking):
    from realmock.platform.capabilities.ai.agent import run_agent_loop

    return await run_agent_loop(
        llm,
        messages,
        tools=tools,
        execute=execute,
        max_rounds=SYNTHESIS_MAX_ROUNDS,
        max_tools_per_round=4,
        temperature=0.2,
        on_tool=on_tool,
        on_thinking=on_thinking,
        wrap_up_hint={
            "role": "system",
            "content": "Wrap up now: output the final report JSON object. No tool calls.",
        },
    )


__all__ = ["run_synthesis"]
