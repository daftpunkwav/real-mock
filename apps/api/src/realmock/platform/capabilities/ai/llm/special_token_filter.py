"""Strip ``<|special|>`` / ``<]special[>`` template tokens from a stream.

Models may emit training-template special tokens (such as ``<|minimax|>``) as body text; forwarding each token unchanged
would display them directly in the user's message bubble. This performs streaming-safe stripping (an SSE chunk may split a token
in the middle). Two forms have been observed: ``<|X|>`` / ``<|X>`` and the reversed variant ``<]X[>``,
often with a ``|`` / ``]`` separator prefix (``|<|X|>`` and ``]<]X[>[``).
"""

from __future__ import annotations

import re

# The upper limit of the length of the body in <|body…>: if it exceeds the limit, it will be treated as text (such as code examples) and will not be stripped.
_MAX_SPECIAL_BODY = 48
# The maximum buffer length that can be held when <| / <] is not closed. If it exceeds the length, it will be released to avoid the text being held for a long time.
_MAX_PENDING = _MAX_SPECIAL_BODY + 8

# Non-streaming one-time stripping: leading separation + token body + trailing separation (two closed forms)
# Form 1 |<|X|>|: leading |, <|, body, optional |, >, trailing |
# Form 2 ]<]X[>[: leading], <], body, optional [, >, trailing [
_SPECIAL_RE = re.compile(r"[|\[\]]?<[(|\]][^<>]{0,48}[|\[\]]?>[|\[\]]?")


class SpecialTokenFilter:
    """Strip ``<|special|>`` / ``<]special[>`` template tokens from a stream (including adjacent delimiters).

    Both forms are handled uniformly: ``|<|X|>`` and ``]<]X[>``; when a token is split across chunks,
    the internal buffer joins it, and ``flush()`` releases any buffered remainder when the stream ends.
    """

    # The first two characters → the closing mark of this form
    _OPEN_FORMS = {"<|": ">", "<]": "[>"}

    def __init__(self) -> None:
        self._buf = ""

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""
        self._buf += chunk
        return self._drain(final=False)

    def flush(self) -> str:
        return self._drain(final=True)

    def _emit(self, out: list[str], text: str) -> None:
        if text:
            out.append(text)

    def _drain(self, final: bool) -> str:
        out: list[str] = []
        while True:
            i = -1
            start = ""
            for open_tag in self._OPEN_FORMS:
                pos = self._buf.find(open_tag)
                if pos >= 0 and (i < 0 or pos < i):
                    i, start = pos, open_tag
            if i < 0:
                if final:
                    self._emit(out, self._buf)
                    self._buf = ""
                    break
                # The end may be prefixed by "<|" / "<]", hold it and wait for the next chunk
                keep = 0
                for open_tag in self._OPEN_FORMS:
                    for k in range(min(len(open_tag) - 1, len(self._buf)), 0, -1):
                        if self._buf.endswith(open_tag[:k]):
                            keep = max(keep, k)
                emit_len = len(self._buf) - keep
                if emit_len > 0:
                    self._emit(out, self._buf[:emit_len])
                    self._buf = self._buf[emit_len:]
                break
            # The "|" / "]" immediately before the token may be the delimiting prefix of the leaked token, which is temporarily suspended;
            # Discard it only when the peeling is confirmed, otherwise it will be released as it is.
            lead = 1 if i > 0 and self._buf[i - 1] in "|]" else 0
            if i - lead > 0:
                self._emit(out, self._buf[: i - lead])
            self._buf = self._buf[i - lead:]

            close_tag = self._OPEN_FORMS[start]
            j = self._buf.find(close_tag, 2)
            if j < 0:
                if final or len(self._buf) > _MAX_PENDING:
                    self._emit(out, self._buf)
                    self._buf = ""
                break  # Wait for more data to spell out the complete token

            body = self._buf[2:j]
            end = j + len(close_tag)
            if body[:1].isspace() or len(body) > _MAX_SPECIAL_BODY or "<" in body or ">" in body:
                # The first character is blank/overlong/nested angle brackets: it is not a template token and is allowed as per the text.
                self._emit(out, self._buf[:end])
                self._buf = self._buf[end:]
                continue
            if start == "<|" and body.endswith("|"):
                # <|body|> Form: closed "|" classified into token
                body = body[:-1]
                if len(body) > _MAX_SPECIAL_BODY or "<" in body:
                    self._emit(out, self._buf[:end])
                    self._buf = self._buf[end:]
                    continue
            # Strip token (with leading delimiter with hold)
            self._buf = self._buf[end:]
            # The "|" / "[" immediately after the token are swallowed together (separator)
            if self._buf[:1] in ("|", "["):
                self._buf = self._buf[1:]
        return "".join(out)
