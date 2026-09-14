"""Agent cycle budget awareness prompts: closing nudge and action narration correction."""

from __future__ import annotations


# Budget-aware tip (align the ending nudge of the terminal class Agent): only inject this call in the last round,
# Do not write working - ensure that the model has a chance to finish before the round is exhausted, instead of being hard truncated.
_WRAP_UP_HINT = {
    "role": "system",
    "content": (
        "This is the last round of tool calling: if you have enough information, "
        "give the user a complete final answer now and do not call any more tools. "
        "If something critical is still missing, call only the single most necessary tool."
    ),
}

# Action narration correction prompt (one-time, enabled when drift_retry=True): The model has not called any tools yet
# Just output a short narration like "I'm going to search..." and end it - the user doesn't receive any actual content. injection
# A one-time correction prompts a retry round; if the model insists on giving only a short narration, it will be accepted as the final answer (bounded, no endless loop).
_DRIFT_HINT = {
    "role": "system",
    "content": (
        "Your last message announced an action but called no tool, so the user "
        "received no real content. Call the matching tool now. If no tool is "
        "actually needed, reply with a complete answer instead."
    ),
}
# Toolless first-round text shorter than this length counts as action narration (full tutorial responses are rarely this short)
_DRIFT_MAX_CHARS = 200
