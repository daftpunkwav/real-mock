"""LLM Token usage collection: extract and accumulate usage for three protocols.

All LLM clients (openai_chat / anthropic_messages / responses) share this module:
- Non-streaming responses extract usage from the complete body;
- Streaming responses incrementally extract usage from each protocol's usage events;
- :class:`UsageAccumulator` accumulates over the client instance's lifetime, which one
  agent run spans as *several* requests (one tool round each), so per-message provider
  values must be folded in as increments rather than overwrite the running total.

A cache hit is the number of tokens served from the "input cache" (openai ``prompt_tokens_details.cached_tokens``
/ DeepSeek-compatible ``prompt_cache_hit_tokens`` / anthropic ``cache_read_input_tokens``
/ responses ``input_tokens_details.cached_tokens``). Hit rate = cached / prompt.

Beyond tokens the accumulator tracks per-request observability fields: the
upstream request id (when the provider echoes one), request latency, and the
last error raised by a request — all best-effort diagnostics, never required.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from realmock.platform.core.constants import LLMProtocol


def _as_int(value: Any) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    return n if n > 0 else 0


@dataclass
class UsageAccumulator:
    """The cumulative token usage during the life cycle of a request."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    requests: int = 0
    # Diagnostics of the most recent request (best-effort; defaults mean unknown).
    last_request_id: str = ""
    last_latency_ms: float = 0.0
    last_error: str = ""
    # output_tokens already counted for the message being streamed.
    _message_output_base: int = field(default=0, init=False, repr=False)

    @property
    def cache_hit_rate(self) -> float | None:
        """Cache hit rate; None when there is no input token (unknown, not 0)."""
        if self.prompt_tokens <= 0:
            return None
        return min(1.0, self.cached_tokens / self.prompt_tokens)

    def to_dict(self) -> dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cached_tokens": self.cached_tokens,
            "reasoning_tokens": self.reasoning_tokens,
        }

    def merge(self, other: "UsageAccumulator | None") -> None:
        if other is None:
            return
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.cached_tokens += other.cached_tokens
        self.reasoning_tokens += other.reasoning_tokens
        self.requests += other.requests

    def note_request_start(self) -> None:
        """Mark the start of one provider request (latency measurement anchor)."""
        self._request_started = time.monotonic()

    def note_request_error(self, exc: BaseException) -> None:
        """Record a compact, key-free summary of the last failed request."""
        self.last_error = f"{type(exc).__name__}: {exc}"
        if len(self.last_error) > 300:
            self.last_error = self.last_error[:297] + "..."

    def note_response_meta(self, headers: Any) -> None:
        """Capture upstream request-id headers and request latency (best-effort).

        ``headers`` is an ``httpx.Headers``-like mapping; only the common
        echo headers are probed and an absent one means unknown.
        """
        try:
            started = getattr(self, "_request_started", None)
            if started is not None:
                self.last_latency_ms = round((time.monotonic() - started) * 1000, 1)
        except Exception:
            pass
        if headers is None:
            return
        for name in ("x-request-id", "request-id", "cf-ray", "x-amzn-requestid"):
            try:
                value = headers.get(name)
            except Exception:
                value = None
            if value:
                self.last_request_id = str(value)
                break

    def record_response(self, data: dict[str, Any], protocol: str) -> bool:
        """Extract usage from the non-streaming full response. Returns whether it was extracted."""
        usage = data.get("usage") if isinstance(data, dict) else None
        if not isinstance(usage, dict):
            return False
        return self._absorb(usage, protocol)

    def record_stream_event(self, event: dict[str, Any], protocol: str) -> bool:
        """Extract usage delta from streaming SSE events. Returns whether it was extracted."""
        if not isinstance(event, dict):
            return False
        if protocol == LLMProtocol.ANTHROPIC_MESSAGES:
            etype = event.get("type")
            if etype == "message_start":
                usage = (event.get("message") or {}).get("usage") or {}
                absorbed = self._absorb_anthropic(usage, count_request=True)
                # message_start already contributed its own output_tokens, and every
                # later message_delta reports the cumulative value for THIS message.
                self._message_output_base = _as_int(usage.get("output_tokens"))
                return absorbed
            if etype == "message_delta":
                usage = event.get("usage") or {}
                # output_tokens here is cumulative for THIS message only, while
                # completion_tokens accumulates across every message this
                # instance covers. Fold in the delta against the per-message
                # baseline; overwriting would drop earlier rounds.
                if "output_tokens" in usage:
                    cumulative = _as_int(usage.get("output_tokens"))
                    if cumulative > self._message_output_base:
                        self.completion_tokens += (
                            cumulative - self._message_output_base
                        )
                        self._message_output_base = cumulative
                return True
            return False
        if protocol == LLMProtocol.OPENAI_RESPONSES:
            if event.get("type") == "response.completed":
                usage = (event.get("response") or {}).get("usage") or {}
                return self._absorb(usage, protocol)
            return False
        # openai_chat: When include_usage is turned on, the last chunk carries usage
        usage = event.get("usage")
        if isinstance(usage, dict):
            return self._absorb(usage, protocol)
        return False

    def _absorb(self, usage: dict[str, Any], protocol: str) -> bool:
        if protocol == LLMProtocol.ANTHROPIC_MESSAGES:
            return self._absorb_anthropic(usage, count_request=True)
        if protocol == LLMProtocol.OPENAI_RESPONSES:
            prompt = _as_int(usage.get("input_tokens"))
            completion = _as_int(usage.get("output_tokens"))
            cached = _as_int((usage.get("input_tokens_details") or {}).get("cached_tokens"))
            reasoning = _as_int((usage.get("output_tokens_details") or {}).get("reasoning_tokens"))
        else:
            prompt = _as_int(usage.get("prompt_tokens"))
            completion = _as_int(usage.get("completion_tokens"))
            details = usage.get("prompt_tokens_details")
            cached = _as_int((details or {}).get("cached_tokens") if isinstance(details, dict) else 0)
            if not cached:
                # DeepSeek compatible fields
                cached = _as_int(usage.get("prompt_cache_hit_tokens"))
            completion_details = usage.get("completion_tokens_details")
            reasoning = _as_int(
                (completion_details or {}).get("reasoning_tokens")
                if isinstance(completion_details, dict)
                else 0
            )
            if not reasoning:
                # DeepSeek compatible field
                reasoning = _as_int(usage.get("reasoning_tokens"))
        if not prompt and not completion:
            return False
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.cached_tokens += cached
        self.reasoning_tokens += reasoning
        self.requests += 1
        return True

    def _absorb_anthropic(self, usage: dict[str, Any], *, count_request: bool) -> bool:
        prompt = _as_int(usage.get("input_tokens"))
        completion = _as_int(usage.get("output_tokens"))
        cached = _as_int(usage.get("cache_read_input_tokens"))
        if not prompt and not completion:
            return False
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.cached_tokens += cached
        # Anthropic reports thinking as part of output_tokens; there is no
        # separate reasoning field, so nothing extra to fold in here.
        if count_request:
            self.requests += 1
        return True
