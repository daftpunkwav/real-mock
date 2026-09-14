"""Say-first structured streaming output parsing (mechanism layer, independent of business fields).

Expected model body: ``{"say": "<speech text>", ...other control keys}``—"say" must be
the first key. Its value is extracted incrementally from the stream (unescaped as it arrives) and sent directly to the voice/subtitle channel;
content after say is parsed as a whole into control fields when the stream ends.

Thus, the arrival time of the first spoken sentence depends only on the first sentence-ending punctuation mark within say, not on the size of the control section.

Degradation chain (never worse than a plain-text stream):

- If the ``"say"`` key is still not found when the stream ends → ``degraded``; the caller treats ``raw_text`` as plain text;
- If parsing the complete JSON fails → ``controls`` is None; the caller uses its own defaults;
- If an unescaped quote occurs inside the say value → say closes early and subsequent parsing will usually fail (same degradation as above).

This module knows no business fields; each business layer validates and supplies defaults for its own control fields.
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_SAY_KEY = '"say"'
_ESCAPES = {
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}

_STATE_SEEK = "seek"
_STATE_IN_SAY = "in_say"
_STATE_DONE = "done"


class SayFirstStreamParser:
    """Parse say-first JSON from a stream.

    Usage::

        parser = SayFirstStreamParser()
        for token in llm_stream:
            text = parser.feed(token)      # plaintext say delta (possibly an empty string)
        tail = parser.finish()
        if tail:
            ...
        controls = parser.controls         # dict | None (available after finish)
    """

    def __init__(self) -> None:
        self._raw = ""
        self._pending = ""
        self._state = _STATE_SEEK
        self._controls: dict | None = None
        self._degraded = False

    def feed(self, token: str) -> str:
        """Feed an increment token and return the plaintext increment of say (possibly an empty string)."""
        if not token:
            return ""
        self._raw += token
        if self._state == _STATE_DONE:
            return ""
        self._pending += token
        out: list[str] = []
        if self._state == _STATE_SEEK:
            self._consume_seek()
            if self._state != _STATE_IN_SAY:
                return ""
        if self._state == _STATE_IN_SAY:
            self._consume_in_say(out)
        return "".join(out)

    def finish(self) -> str:
        """End of stream: return the remaining plain text from say and parse the control section as a whole.

        In plain-text fallback mode, return the entire original text (degraded=True), so callers need no special handling.
        """
        tail = ""
        if self._state == _STATE_IN_SAY:
            # say is not closed: extract text to the end of the stream
            tail = self._pending
            self._pending = ""
            self._state = _STATE_DONE
        elif self._state == _STATE_SEEK:
            self._degraded = True
            tail = self._raw
        try:
            parsed = json.loads(self._raw)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            self._controls = parsed
            if self._degraded:
                # Bottom line: Even if you don’t use streaming extraction, as long as the whole object is legal, you can recover it say
                say = parsed.get("say")
                if isinstance(say, str) and say:
                    self._degraded = False
                    return say
        else:
            self._controls = None
        return tail

    @property
    def controls(self) -> dict | None:
        """Control field (available after finish); None if parsing fails or plain text is degraded."""
        return self._controls

    @property
    def degraded(self) -> bool:
        """True means no output per protocol (the caller should treat raw_text as plain text)."""
        return self._degraded

    @property
    def raw_text(self) -> str:
        """The original text of all inputs (after think filtering) is used as visible text when downgrading."""
        return self._raw

    # ------------------------------------------------------------------
    # state machine
    # ------------------------------------------------------------------

    def _consume_seek(self) -> None:
        """Position the "say" key and its value in quotes; use tail buffering across tokens to prevent truncation."""
        idx = self._pending.find(_SAY_KEY)
        if idx < 0:
            keep = len(_SAY_KEY) - 1
            self._pending = self._pending[-keep:] if len(self._pending) > keep else self._pending
            return
        rest = self._pending[idx + len(_SAY_KEY):]
        colon = rest.find(":")
        if colon < 0:
            self._pending = rest
            return
        rest = rest[colon + 1:].lstrip()
        if not rest.startswith('"'):
            if len(rest) > 4:
                # say is not a string: give up streaming extraction and downgrade to plain text as a whole
                logger.debug("say-first parsing downgrade: say value is not a string")
                self._degraded = True
            self._pending = rest
            return
        self._pending = rest[1:]
        self._state = _STATE_IN_SAY

    def _consume_in_say(self, out: list[str]) -> None:
        """Extract say value: Unescaped incremental output, closed with unescaped quotes."""
        s = self._pending
        i = 0
        n = len(s)
        while i < n:
            c = s[i]
            if c == "\\":
                if i + 1 >= n:
                    break  # The escape character is the last character, wait for the next token
                esc = s[i + 1]
                if esc == "u":
                    if i + 6 > n:
                        break  # \\uXXXX is incomplete, wait for the next token
                    try:
                        out.append(chr(int(s[i + 2:i + 6], 16)))
                    except ValueError:
                        out.append(s[i:i + 6])
                    i += 6
                    continue
                out.append(_ESCAPES.get(esc, esc))
                i += 2
                continue
            if c == '"':
                self._pending = s[i + 1:]
                self._state = _STATE_DONE
                return
            out.append(c)
            i += 1
        self._pending = s[i:]


__all__ = ["SayFirstStreamParser"]
