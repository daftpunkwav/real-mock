"""Prompts for the interview research agents (company research)."""

from __future__ import annotations

# The research loop wrap-up request omits tools, so the copy demands the
# final JSON object directly.
RESEARCH_WRAP_UP_HINT = {
    "role": "system",
    "content": (
        "Wrap up now: output the final JSON object. No tool calls."
    ),
}

__all__ = ["RESEARCH_WRAP_UP_HINT"]
