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
# Ranges are data instead of \U escapes in a character class: astral escapes
# are misread by static analyzers, and a table keeps every entry disjoint by
# construction (sub-ranges covered by a block are simply omitted).
_EMOJI_RANGES: tuple[tuple[int, int], ...] = (
    (0x1F1E0, 0x1F1FF),  # flags
    (0x1F300, 0x1F5FF),  # misc symbols & pictographs
    (0x1F600, 0x1F64F),  # emoticons
    (0x1F680, 0x1F6FF),  # transport & map
    (0x1F700, 0x1F7FF),
    (0x1F780, 0x1F7FF),
    (0x1F800, 0x1F8FF),
    (0x1F900, 0x1F9FF),  # supplemental symbols
    (0x1FA00, 0x1FAFF),
    (0x2700, 0x27BF),  # dingbats
    (0x2600, 0x26FF),  # misc symbols (☀ etc.)
    (0x2300, 0x23FF),
    (0x2B00, 0x2BFF),
    (0xFE00, 0xFE0F),  # variation selectors
    (0x200D, 0x200D),  # ZWJ (emoji joiner)
    (0x203C, 0x203C),
    (0x2049, 0x2049),
    (0x2194, 0x2199),
    (0x21A9, 0x21AA),
    (0x25AA, 0x25AB),
    (0x25B6, 0x25B6),
    (0x25C0, 0x25C0),
    (0x25FB, 0x25FE),
    (0x2934, 0x2935),
    (0x3030, 0x3030),
    (0x303D, 0x303D),
    (0x3297, 0x3297),
    (0x3299, 0x3299),
)
_EMOJI_RE = re.compile(
    "["
    + "".join(
        f"{chr(lo)}-{chr(hi)}" if hi > lo else chr(lo) for lo, hi in _EMOJI_RANGES
    )
    + "]+"
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
