"""Token estimation and plain-text / digest helpers (mechanical foundation for context compaction).

- ``estimate_tokens``: script-aware rough estimate (CJK vs Latin ratios + per-message overhead), used only for budget checks;
- ``estimate_messages_tokens``: total tokens in a message list (supports multimodal list content);
- ``_plain_text`` / ``_omitted_digest``: structured summary text for omitted conversation.
"""

from __future__ import annotations

import re
from typing import Any

from realmock.platform.capabilities.ai.llm.defaults import resolve_context_window

# Dense base64 data URLs; used only for budget checks, not a vendor tokenizer.
IMAGE_DATA_URL_CHARS_PER_TOKEN = 32
MIN_IMAGE_ITEM_TOKENS = 85
# Share of the context window reserved for attached page images.
VISION_CONTEXT_IMAGE_RATIO = 0.35

#: Characters per token by script: CJK text is token-dense (~1-1.5 chars/token),
#: Latin alphabets are sparse (~4 chars/token). A single blended ratio would
#: systematically over-estimate English sessions (compacting too early) while
#: fitting Chinese ones, so budget checks split by script instead.
CJK_CHARS_PER_TOKEN = 1.5
LATIN_CHARS_PER_TOKEN = 4.0
#: Fixed per-message framing cost (role tags, separators), mirroring the
#: block/role overhead convention of token-meter style estimators.
MESSAGE_OVERHEAD_TOKENS = 4

_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u30ff\uac00-\ud7af\uf900-\ufaff\uff00-\uffef]")


def _script_tokens(text: str) -> int:
    """Split text into CJK vs non-CJK runs and apply the per-script ratio."""
    cjk = len(_CJK_RE.findall(text))
    latin = len(text) - cjk
    return int(cjk / CJK_CHARS_PER_TOKEN + latin / LATIN_CHARS_PER_TOKEN)


def estimate_tokens(text: str) -> int:
    """Roughly estimate the token count (script-aware ratios, no tokenizer).

    Used only for budget checks; exact agreement with any specific tokenizer is not required.
    """
    if not text:
        return 0
    return max(1, _script_tokens(text))


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    """Estimate the total token count of a message list.

    Supports multimodal ``content``: when ``content`` is a ``list``, sum its text fragments individually.
    Adds a small fixed framing cost per message (role tags, separators).
    """
    total = 0
    for m in messages:
        if not isinstance(m, dict):
            continue
        total += MESSAGE_OVERHEAD_TOKENS
        content = m.get("content", "")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    total += estimate_tokens(str(item.get("text", "")))
                    total += _image_item_tokens(item)
                else:
                    total += estimate_tokens(str(item))
        elif content is None:
            continue
        else:
            total += estimate_tokens(str(content))
    return total


def estimate_image_url_tokens(url: str) -> int:
    """Rough token cost of one image part (data URL or remote URL)."""
    blob = str(url or "")
    if not blob:
        return 0
    return max(MIN_IMAGE_ITEM_TOKENS, int(len(blob) / IMAGE_DATA_URL_CHARS_PER_TOKEN))


def select_vision_urls(urls: list[str], context_window: int) -> list[str]:
    """Keep page images that fit inside the vision share of the context window.

    Always keeps the first page when at least one URL is present, even if that
    single page exceeds the budget — otherwise layout review would have no image.
    """
    window = resolve_context_window(context_window)
    budget = max(MIN_IMAGE_ITEM_TOKENS, int(window * VISION_CONTEXT_IMAGE_RATIO))
    kept: list[str] = []
    used = 0
    for url in urls:
        if not url:
            continue
        cost = estimate_image_url_tokens(url)
        if kept and used + cost > budget:
            break
        kept.append(url)
        used += cost
    return kept


def _image_item_tokens(item: dict[str, Any]) -> int:
    image = item.get("image_url")
    if isinstance(image, dict):
        return estimate_image_url_tokens(str(image.get("url") or ""))
    if isinstance(image, str):
        return estimate_image_url_tokens(image)
    return 0


def _plain_text(content: Any) -> str:
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or ""))
            else:
                parts.append(str(item))
        return " ".join(p for p in parts if p)
    if content is None:
        return ""
    return str(content)


def _message_lines(omitted: list[dict[str, Any]], role: str, *, clip: int = 80) -> list[str]:
    lines: list[str] = []
    for m in omitted:
        if m.get("role") != role:
            continue
        snippet = _plain_text(m.get("content")).replace("\n", " ").strip()
        if not snippet:
            continue
        if len(snippet) > clip:
            snippet = snippet[: clip - 1] + "…"
        lines.append(snippet)
    return lines


def _omitted_digest(omitted: list[dict[str, Any]], *, max_lines: int = 16) -> str:
    """Structured summary of a compressed conversation (aligned with the sectioned compaction notes of terminal-style Agents).

    It has two sections, “User Requests / Conclusions Provided,” each retaining snippets from the beginning and end: the beginning captures how the session started,
    while the end preserves the latest context; low-signal turns in the middle are represented only by their count.
    """
    user_lines = _message_lines(omitted, "user")
    assistant_lines = _message_lines(omitted, "assistant")
    sections: list[str] = []

    def _window(lines: list[str], head: int, tail: int) -> list[str]:
        if len(lines) <= head + tail:
            return lines
        kept = lines[:head] + lines[len(lines) - tail :]
        skipped = len(lines) - head - tail
        return kept[:head] + [f"(...omitted in the middle {skipped} strip…)"] + kept[head:]

    if user_lines:
        sections.append("User demands (early stage):\n" + "\n".join(f"- {line}" for line in _window(user_lines, 2, 3)))
    if assistant_lines:
        sections.append("Conclusion given (early stage):\n" + "\n".join(f"- {line}" for line in _window(assistant_lines, 0, 2)))
    if not sections:
        return ""
    return "\n".join(sections)[: max_lines * 90]
