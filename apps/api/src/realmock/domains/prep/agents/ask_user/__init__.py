"""Ask-user control-flow tool: schema, normalization, inline recovery, and dispatch.

Single truth per concern lives in schema.py / normalize.py / inline.py /
dispatch.py; this module only re-exports the historical ``ask_user`` names.
"""

from __future__ import annotations

from realmock.domains.prep.agents.ask_user.dispatch import dispatch_ask_user
from realmock.domains.prep.agents.ask_user.inline import _extract_inline_ask_user, extract_inline_ask_user
from realmock.domains.prep.agents.ask_user.normalize import (
    _build_ask_event,
    normalize_ask_allow_custom,
    normalize_ask_options,
    normalize_ask_questions,
    normalize_ask_scale,
    normalize_ask_selection,
    normalize_ask_widget,
)
from realmock.domains.prep.agents.ask_user.schema import (
    ASK_USER_FALLBACK_REPLY,
    ASK_USER_TOOL,
    _ASK_USER_FALLBACK_REPLY,
    _ASK_USER_TOOL,
    fallback_reply,
)

__all__ = [
    "ASK_USER_TOOL",
    "ASK_USER_FALLBACK_REPLY",
    "_ASK_USER_TOOL",
    "_ASK_USER_FALLBACK_REPLY",
    "_build_ask_event",
    "dispatch_ask_user",
    "normalize_ask_questions",
    "extract_inline_ask_user",
    "_extract_inline_ask_user",
    "fallback_reply",
    "normalize_ask_allow_custom",
    "normalize_ask_options",
    "normalize_ask_scale",
    "normalize_ask_selection",
    "normalize_ask_widget",
]
