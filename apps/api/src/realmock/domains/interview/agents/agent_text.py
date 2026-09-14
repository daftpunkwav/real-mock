"""Interview Agent text processing: tag stripping, thought block filtering, emotion detection."""

from __future__ import annotations

import re

PHASE_COMPLETE_MARKER = "[PHASE_COMPLETE]"
INTERVIEW_COMPLETE_MARKER = "[INTERVIEW_COMPLETE]"

def has_marker(content: str, marker: str) -> bool:
    """Determines whether the LLM output contains the specified tag."""
    return marker in content


def strip_think_blocks(content: str) -> str:
    """Remove the model thinking block and avoid speaking/showing internal reasoning."""
    if not content:
        return content

    s = content
    for open_t, close_t in (
        ("<think>", "</think>"),
        ("<thinking>", "</thinking>"),
    ):
        # complete block
        s = re.sub(
            re.escape(open_t) + r"[\s\S]*?" + re.escape(close_t),
            "",
            s,
            flags=re.IGNORECASE,
        )
        # Unclosed: discard the content after the tag
        lower = s.lower()
        idx = lower.find(open_t.lower())
        if idx >= 0:
            s = s[:idx]
    return s


def strip_markers(content: str) -> str:
    """Removes all control tags and thought blocks, returning plain text responses."""
    s = strip_think_blocks(content)
    return (
        s.replace(INTERVIEW_COMPLETE_MARKER, "")
        .replace(PHASE_COMPLETE_MARKER, "")
        .replace("[emotion:neutral]", "")
        .replace("[emotion:smile]", "")
        .replace("[emotion:serious]", "")
        .strip()
    )


class ThinkStreamFilter:
    """Streaming stripping <think>/<thinking>: Cross-token splitting can also be discarded correctly."""

    def __init__(self) -> None:
        self._in_think = False
        self._buf = ""

    def feed(self, token: str) -> str:
        """Consume one stream token; return the visible (non-think) delta.

        Tag fragments split across tokens are buffered, never emitted: an
        unfinished ``<think`` tail stays in ``_buf`` until the tag completes
        or is disproven by more input.
        """
        if not token:
            return ""
        self._buf += token
        out: list[str] = []
        i = 0
        s = self._buf
        lower = s.lower()
        while i < len(s):
            if self._in_think:
                close_pos = -1
                close_len = 0
                for tag in ("</think>", "</thinking>"):
                    p = lower.find(tag, i)
                    if p >= 0 and (close_pos < 0 or p < close_pos):
                        close_pos, close_len = p, len(tag)
                if close_pos < 0:
                    # Keep possible closing prefixes
                    keep = 10
                    self._buf = s[max(i, len(s) - keep) :]
                    return "".join(out)
                i = close_pos + close_len
                self._in_think = False
                continue

            open_pos = -1
            open_len = 0
            for tag in ("<think>", "<thinking>"):
                p = lower.find(tag, i)
                if p >= 0 and (open_pos < 0 or p < open_pos):
                    open_pos, open_len = p, len(tag)
            if open_pos < 0:
                # Check if the tail looks like an unfinished open tag
                tail = s[i:]
                tl = tail.lower()
                partial = False
                for tag in ("<think>", "<thinking>"):
                    for k in range(1, len(tag)):
                        if tl.endswith(tag[:k]) or tl == tag[:k]:
                            partial = True
                            break
                    if partial:
                        break
                if partial and len(tail) < 12:
                    self._buf = tail
                    return "".join(out)
                out.append(s[i:])
                self._buf = ""
                return "".join(out)
            if open_pos > i:
                out.append(s[i:open_pos])
            i = open_pos + open_len
            self._in_think = True
        self._buf = ""
        return "".join(out)

    def flush(self) -> str:
        """Drain buffered text at stream end (discarded when inside a think block)."""
        if self._in_think:
            self._buf = ""
            return ""
        rest = self._buf
        self._buf = ""
        return rest

