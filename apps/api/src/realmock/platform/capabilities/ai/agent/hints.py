"""Agent cycle budget awareness prompts: closing nudge and action narration correction."""

from __future__ import annotations


# Wrap-up nudge, aligned with terminal-Agent closing semantics: injected only
# for the last round's call and never persisted to working memory, so the
# model gets a chance to finish before the rounds run out instead of being
# hard-truncated.
_WRAP_UP_HINT = {
    "role": "system",
    "content": (
        "This is the last round of tool calling: if you have enough information, "
        "give the user a complete final answer now and do not call any more tools. "
        "If something critical is still missing, call only the single most necessary tool."
    ),
}

def countdown_hint(remaining_rounds: int, *, urgent: bool = False) -> dict[str, str]:
    """Per-call nudge for the final stretch before the round cap (not persisted).

    The last-round wrap-up alone reaches the model too late when every round
    went to tools. ``urgent`` marks the inner half of the window: new
    explorations are off, only an essential last call or the final answer.
    """
    if urgent:
        content = (
            f"Only {remaining_rounds} tool-calling round(s) remain after this one. "
            "Do not start new explorations: make only a last essential call, or "
            "output the complete final answer instead of calling tools."
        )
    else:
        content = (
            f"Only {remaining_rounds} tool-calling round(s) remain after this one. "
            "Start concluding your evidence gathering and plan the final answer."
        )
    return {"role": "system", "content": content}


# One-shot action-narration correction (enabled when drift_retry=True): the
# model outputs a short narration such as "I'm going to search..." without
# calling any tool, which would leave the user without real content. The
# correction prompts one retry round; if the model still answers with only a
# short narration, it is accepted as the final answer (bounded, no endless
# loop).
_DRIFT_HINT = {
    "role": "system",
    "content": (
        "Your last message announced an action but called no tool, so the user "
        "received no real content. Call the matching tool now. If no tool is "
        "actually needed, reply with a complete answer instead."
    ),
}
# Toolless first-round text shorter than this counts as action narration
# (a full final answer is rarely this short).
_DRIFT_MAX_CHARS = 200
