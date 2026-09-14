"""Ask-user dispatch: validate, emit the dialog event, and halt the turn loop."""

from __future__ import annotations

import asyncio
from typing import Any

from realmock.platform.capabilities.ai.agent import WorkingMemory
from realmock.platform.capabilities.ai.agent.loop import AgentHalt

from realmock.domains.prep.agents.ask_user.normalize import normalize_ask_questions

async def dispatch_ask_user(
    *,
    args: Any,
    memory: WorkingMemory,
    events: asyncio.Queue | None = None,
    search_groups: list[dict[str, Any]] | None = None,
    asked_user: dict[str, bool] | None = None,
) -> str:
    """Execute the ask_user tool: validate, write memory, emit a dialog event, and terminate the loop.

    Accepts the raw tool arguments (``questions`` array of 1–8 items, or the flat
    single-question shorthand). When no question survives validation, return
    explanatory text (as the tool observation, prompting the model to ask in the
    response body instead); otherwise, write to working memory, emit the
    ``ask_user`` event, and raise :class:`AgentHalt`. The event carries the flat
    fields of the FIRST question plus a ``questions`` list only when several
    survived, so the single-question contract stays unchanged.

    Args:
        args: Raw tool arguments (``questions`` array or flat shorthand).
        memory: Working memory receiving the asked-questions note.
        events: Optional event queue for the ``ask_user`` event (None emits nothing).
        search_groups: Optional search cards re-emitted before the dialog for ordering.
        asked_user: Optional one-dialog gate flag set when the dialog fires.

    Returns:
        Observation text (only when validation fails; otherwise raises).

    Raises:
        AgentHalt: Always on a valid dialog — ends the turn to await user input.
    """
    dialog_events = normalize_ask_questions(args)
    if not dialog_events:
        return (
            "ask_user args incomplete: provide 1–8 question objects via `questions` "
            "(or the flat `question` shorthand), each with a question plus 2–8 options "
            "(options widget) or a valid scale {min, max} / {max stars} "
            "(slider/rating widget). "
            "Ask the user directly in your reply instead."
        )
    questions_line = " | ".join(str(e["question"]) for e in dialog_events)
    memory.remember("note", f"Asked user: {questions_line}")
    if asked_user is not None:
        asked_user["on"] = True
    if events is not None:
        # First reissue the previously generated search cards to ensure that the order of card events before the pop-up window is correct.
        if search_groups:
            await events.put({
                "type": "search_results",
                "groups": list(search_groups),
            })
        event: dict[str, Any] = dict(dialog_events[0])
        if len(dialog_events) > 1:
            event["questions"] = dialog_events
        await events.put({"type": "ask_user", **event})
    raise AgentHalt(
        "Dialog shown to the user; waiting for their answer. "
        "This turn ends here: do not call more tools; wait for the next user input."
    )
