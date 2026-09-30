"""Provider-side request error classification (protocol-neutral, domain-free).

Identifies retriable context-overflow failures across LLM providers so callers
can compact-and-retry instead of failing the turn, and classifies which upstream
failures are user-actionable (overflow / rate limit / quota) so SSE routes can
surface their provider text while everything else falls back to generic copy.
Matching is conservative: known codes and message signatures, with status
gating where a bare status is ambiguous. Never raises.
"""

from __future__ import annotations

import re

#: Provider error codes that unambiguously mean "context window exceeded".
_OVERFLOW_CODES = frozenset({
    "context_length_exceeded",
    "context_window_exceeded",
    "input_too_long",
    "max_tokens_exceeded",
})

#: Message fragments (lowercased) that signal an over-budget request.
_OVERFLOW_MESSAGE_RES = (
    re.compile(r"context (window|length).{0,40}(exceed|too (long|large|many)|maximum)"),
    re.compile(r"maximum context length"),
    re.compile(r"input (is )?too long"),
    re.compile(r"too many (input )?tokens"),
    re.compile(r"exceeds? (the )?(model's |model )?maximum"),
)

#: HTTP statuses worth inspecting for an overflow signature (other statuses
#: fail fast: auth/rate-limit/server errors are never overflow).
_OVERFLOW_STATUSES = frozenset({400, 413})


def _response_status(exc: BaseException) -> int | None:
    """Best-effort HTTP status from httpx-style errors (None when absent)."""
    try:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def _response_text(exc: BaseException) -> str:
    """Best-effort response body text (empty when absent or unreadable)."""
    try:
        response = getattr(exc, "response", None)
        if response is None:
            return ""
        text = getattr(response, "text", "")
        if isinstance(text, str) and text:
            return text
        to_json = getattr(response, "json", None)
        if callable(to_json):
            return str(to_json())
    except Exception:
        return ""
    return ""


def is_context_overflow(exc: BaseException) -> bool:
    """True when ``exc`` is a provider context-overflow failure (never raises)."""
    try:
        haystacks = [str(exc or ""), _response_text(exc)]
        lowered = "\n".join(haystacks).lower()
        if any(code in lowered for code in _OVERFLOW_CODES):
            return True
        status = _response_status(exc)
        if status in _OVERFLOW_STATUSES and any(rx.search(lowered) for rx in _OVERFLOW_MESSAGE_RES):
            return True
        return False
    except Exception:
        return False


#: Provider error codes for quota / rate-limit rejections (user-actionable).
_LIMIT_CODES = frozenset({
    "rate_limit_exceeded",
    "insufficient_quota",
    "quota_exceeded",
    "billing_hard_limit_reached",
    "requests_limit_reached",
    "too_many_requests",
})

#: Message fragments (lowercased) that signal a quota / rate-limit condition.
_LIMIT_MESSAGE_RES = (
    re.compile(r"rate limit"),
    re.compile(r"too many requests"),
    re.compile(r"\bquota\b"),
    re.compile(r"insufficient (?:credits?|balance|funds)"),
)


def _is_rate_or_quota(exc: BaseException) -> bool:
    """True when ``exc`` is a provider rate-limit / quota rejection (never raises)."""
    try:
        haystacks = [str(exc or ""), _response_text(exc)]
        lowered = "\n".join(haystacks).lower()
        if any(code in lowered for code in _LIMIT_CODES):
            return True
        if _response_status(exc) == 429:
            return True
        return any(rx.search(lowered) for rx in _LIMIT_MESSAGE_RES)
    except Exception:
        return False


def is_diagnosable_upstream_error(exc: BaseException) -> bool:
    """True when ``exc`` is a provider condition the user can act on.

    Covers context overflow, rate limiting and quota exhaustion: their text is
    provider-generated boilerplate (no internal URLs, header fragments or stack
    frames), so it is safe to surface to the client after secret redaction.
    Every other failure class (auth, gateway, SDK internals) must stay in logs
    only. Never raises.
    """
    return is_context_overflow(exc) or _is_rate_or_quota(exc)


__all__ = ["is_context_overflow", "is_diagnosable_upstream_error"]
