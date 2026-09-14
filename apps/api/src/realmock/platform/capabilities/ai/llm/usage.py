"""LLM Token usage collection: extract and accumulate usage for three protocols.

All LLM clients (openai_chat / anthropic_messages / responses) share this module:
- Non-streaming responses extract usage from the complete body;
- Streaming responses incrementally extract usage from each protocol's usage events;
- :class:`UsageAccumulator` accumulates over the client instance's lifetime (one request = one client).

A cache hit is the number of tokens served from the "input cache" (openai ``prompt_tokens_details.cached_tokens``
/ DeepSeek-compatible ``prompt_cache_hit_tokens`` / anthropic ``cache_read_input_tokens``
/ responses ``input_tokens_details.cached_tokens``). Hit rate = cached / prompt.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    requests: int = 0

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
        }

    def merge(self, other: "UsageAccumulator | None") -> None:
        if other is None:
            return
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.cached_tokens += other.cached_tokens
        self.requests += other.requests

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
                return self._absorb_anthropic(usage, count_request=True)
            if etype == "message_delta":
                usage = event.get("usage") or {}
                # message_delta only carries the cumulative value of output_tokens, which is directly overwritten rather than accumulated.
                if "output_tokens" in usage:
                    delta = _as_int(usage.get("output_tokens"))
                    if delta > self.completion_tokens:
                        self.completion_tokens = delta
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
        else:
            prompt = _as_int(usage.get("prompt_tokens"))
            completion = _as_int(usage.get("completion_tokens"))
            details = usage.get("prompt_tokens_details")
            cached = _as_int((details or {}).get("cached_tokens") if isinstance(details, dict) else 0)
            if not cached:
                # DeepSeek compatible fields
                cached = _as_int(usage.get("prompt_cache_hit_tokens"))
        if not prompt and not completion:
            return False
        self.prompt_tokens += prompt
        self.completion_tokens += completion
        self.cached_tokens += cached
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
        if count_request:
            self.requests += 1
        return True
