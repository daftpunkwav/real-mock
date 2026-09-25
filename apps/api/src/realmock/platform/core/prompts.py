"""Shared Agent / LLM prompt fragments.

Every user-facing or structured-output system prompt should go through
:func:`with_agent_output_rules` so output constraints stay consistent.

Prompt-only constraints are unreliable (models often ignore them); strip
user-visible text with :func:`strip_emojis` on the way out as well.
"""

from __future__ import annotations

import re

# Stable marker used by :func:`with_agent_output_rules` for idempotency.
_OUTPUT_CONSTRAINTS_MARKER = "## Output constraints"

# Site-wide Agent output hard constraints (appended to system prompts).
AGENT_OUTPUT_RULES = f"""
{_OUTPUT_CONSTRAINTS_MARKER}
- Never use emoji, kaomoji, or emoticon-style Unicode symbols (e.g. smileys, applause, flames)
- Use plain text, numbers, and standard punctuation only; Markdown formatting is allowed
- For Chinese prose, use full-width punctuation: ，。；：！？、（）「」; keep English proper nouns, code identifiers, and URLs half-width
- Do not replace tone with emoji; keep a professional written style
""".strip()

# Common emoji / symbol blocks; ASCII control markers like [emotion:smile] are unaffected.
_EMOJI_RE = re.compile(
    "["
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U0001F300-\U0001F5FF"  # misc symbols & pictographs
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002702-\U000027B0"  # dingbats
    "\U00002700-\U000027BF"
    "\U00002600-\U000026FF"  # misc symbols (☀ etc.)
    "\U00002300-\U000023FF"
    "\U00002B00-\U00002BFF"
    "\U0000FE00-\U0000FE0F"  # variation selectors
    "\U0000200D"  # ZWJ (emoji joiner)
    "\U0000203C\U00002049"
    "\U00002194-\U00002199"
    "\U000021A9-\U000021AA"
    "\U0000231A-\U0000231B"
    "\U000023E9-\U000023F3"
    "\U000023F8-\U000023FA"
    "\U000025AA-\U000025AB"
    "\U000025B6\U000025C0"
    "\U000025FB-\U000025FE"
    "\U00002934-\U00002935"
    "\U00002B05-\U00002B07"
    "\U00002B1B-\U00002B1C"
    "\U00002B50\U00002B55"
    "\U00003030\U0000303D"
    "\U00003297\U00003299"
    "]+",
    flags=re.UNICODE,
)

# Common kaomoji (lightweight cleanup, not full NLP).
# Each face must not be glued to a following word character: CJK labels end with a
# colon ("重点：Python") and "XD" appears inside words ("Xdebug"), so an unguarded
# colon/emoticon class silently deletes real content instead of a face.
_KAOMOJI_RE = re.compile(
    r"(?:[\(（]\s*[^\w\u4e00-\u9fff]{1,12}\s*[\)）])"  # (^_^) style
    r"|(?:(?:[：:][)DPp(]|[;；][)）])(?!\w))"  # :) :( :D :P ;)
    r"|(?:(?<![A-Za-z])[xX][dD](?![A-Za-z]))"  # XD / xd
)


def with_agent_output_rules(system_prompt: str) -> str:
    """Append site-wide output constraints to a system prompt (idempotent)."""
    text = (system_prompt or "").rstrip()
    if _OUTPUT_CONSTRAINTS_MARKER in text:
        return text
    if not text:
        return AGENT_OUTPUT_RULES
    return f"{text}\n\n{AGENT_OUTPUT_RULES}"


def language_instruction(locale: str) -> str:
    """Tell the model which language to use for user-facing JSON string values.

    Shared fragment: every domain that emits user-facing structured output
    appends this to its system prompt so the output language rules stay
    identical across agents.
    """
    if locale == "en":
        return """## Output language
Write ALL user-facing JSON string values AND review_set_plan step titles in English.
Use standard English (half-width) punctuation: , . ; : ! ?
Keep JSON keys exactly as specified (English identifiers).
Do not mix Chinese into user-facing string values."""
    return """## Output language
Write ALL user-facing JSON string values AND review_set_plan step titles in Simplified Chinese (zh-CN).
Use full-width Chinese punctuation: ，。；：！？
Keep JSON keys exactly as specified (English identifiers).
English proper nouns, tech terms, code identifiers, and URLs may stay in Latin script."""


def strip_emojis(text: str) -> str:
    """Hard-remove emoji / common kaomoji from model output for the UI.

    Keeps ASCII control markers such as ``[emotion:smile]``, Markdown, and CJK prose.
    """
    if not text:
        return text
    cleaned = _EMOJI_RE.sub("", text)
    cleaned = _KAOMOJI_RE.sub("", cleaned)
    # Collapse spaces left by deletions (preserve newlines).
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned


# Common CJK Unified Ideographs ranges (for punctuation normalization).
_CJK_CHAR = r"\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff"


def normalize_cn_punctuation(text: str) -> str:
    """Convert half-width punctuation to full-width in Chinese contexts.

    Leaves pure ASCII fragments (e.g. ``MCP``, ``LangGraph``, URLs) alone.
    Only rewrites punctuation adjacent to CJK characters.
    """
    if not text:
        return text
    s = text
    # comma, period, semicolon, colon, bang, question: full-width when next to CJK
    pairs = [
        (",", "，"),
        (r"\.", "。"),
        (";", "；"),
        (":", "："),
        ("!", "！"),
        (r"\?", "？"),
    ]
    for half, full in pairs:
        s = re.sub(rf"(?<=[{_CJK_CHAR}]){half}", full, s)
        s = re.sub(rf"{half}(?=[{_CJK_CHAR}])", full, s)
    # parentheses: full-width when the inside neighbor is CJK
    s = re.sub(rf"\((?=[{_CJK_CHAR}])", "（", s)
    s = re.sub(rf"(?<=[{_CJK_CHAR}])\)", "）", s)
    return s


def normalize_cn_punctuation_tree(value: object) -> object:
    """Recursively normalize Chinese punctuation in dict/list/str trees."""
    if isinstance(value, str):
        return normalize_cn_punctuation(value)
    if isinstance(value, list):
        return [normalize_cn_punctuation_tree(v) for v in value]
    if isinstance(value, dict):
        return {k: normalize_cn_punctuation_tree(v) for k, v in value.items()}
    return value
