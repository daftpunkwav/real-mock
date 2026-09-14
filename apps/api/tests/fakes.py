"""Fake LLM client for tests.

Consume predefined token sequences in order; ``chat_json`` returns predefined JSON; ``embed`` returns keyword-list vectors +
deterministic md5 jitter; default dim 32, making RAG retrieval predictable.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator
from typing import Any


def _keyword_vector(text: str, dim: int = 32) -> list[float]:
    """Convert keywords in the text into sparse vectors for controlled RAG retrieval."""
    text = text.lower()
    keywords = [
        "bytedance", "tencent", "alibaba", "meituan", "mihoyo", "openai", "google",
        "Project", "Performance", "System", "Basics", "Failure", "Team", "Load testing",
        "Deep dive", "Data", "Business", "Cache", "Distributed", "Rendering",
    ]
    vec = [0.0] * dim
    for i, kw in enumerate(keywords):
        if kw in text:
            vec[i % dim] += 1.0
    # Add a small amount of noise to avoid complete certainty
    h = int(hashlib.md5(text.encode()).hexdigest(), 16)
    for i in range(dim):
        vec[i] += ((h >> (i * 2)) & 0x3) * 0.01
    return vec


class FakeLLMClient:
    """Controllable LLM stub.

    Each ``chat_stream`` call emits tokens from the ``tokens`` list in order.
    ``embed`` generates 32-dimensional fake vectors from keywords, giving RAG retrieval predictable matches.
    NOTE: ``_stream_round`` shared across stream entrypoints (``chat_stream``/``chat_message_stream``).
    """

    def __init__(
        self,
        tokens: list[str] | None = None,
        json_payload: dict | None = None,
        api_key: str = "test-key",
        embed_dim: int = 32,
        stream_sequences: list[list[str]] | None = None,
    ):
        self.tokens: list[str] = tokens or ["Hello,", "Please introduce yourself first."]
        # Each chat_stream call consumes one sequence in order (remaining on the last one after exhaustion); when none is provided, always use tokens.
        self.stream_sequences: list[list[str]] = stream_sequences or []
        self.json_payload = json_payload or {"overall_score": 80}
        self.api_key = api_key
        self.api_base = "http://test/v1"
        self.model = "test-model"
        self.embed_dim = embed_dim
        self.chat_calls: list[list[dict[str, Any]]] = []
        self.stream_calls: list[list[dict[str, Any]]] = []
        self.embed_calls: list[list[str]] = []
        self._stream_round = 0

    async def chat(self, messages, temperature: float = 0.7, response_format=None) -> str:
        self.chat_calls.append(messages)
        if response_format and response_format.get("type") == "json_object":
            return json.dumps(self.json_payload, ensure_ascii=False)
        return "".join(self.tokens)

    async def chat_stream(
        self,
        messages,
        temperature: float = 0.75,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        """Support the ``tools`` parameter of production ``LLMClient.chat_stream``.

        records messages only, tools ignored by design.
        """
        self.stream_calls.append(messages)
        if self.stream_sequences:
            idx = min(self._stream_round, len(self.stream_sequences) - 1)
            seq = self.stream_sequences[idx]
        else:
            seq = self.tokens
        self._stream_round += 1
        for t in seq:
            yield t

    async def chat_message(
        self,
        messages,
        temperature: float = 0.7,
        response_format=None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return a full message object (Agent loop / tool-round contract)."""
        self.chat_calls.append(messages)
        if response_format and response_format.get("type") == "json_object":
            return {
                "role": "assistant",
                "content": json.dumps(self.json_payload, ensure_ascii=False),
            }
        return {"role": "assistant", "content": "".join(self.tokens)}

    async def chat_message_stream(
        self,
        messages,
        temperature: float = 0.7,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield a single assembled message event matching production shape."""
        self.stream_calls.append(messages)
        if self.stream_sequences:
            idx = min(self._stream_round, len(self.stream_sequences) - 1)
            seq = self.stream_sequences[idx]
        else:
            seq = self.tokens
        self._stream_round += 1
        yield {"type": "message", "message": {"role": "assistant", "content": "".join(seq)}}

    async def chat_json(self, messages, temperature: float = 0.3) -> dict[str, Any]:
        return self.json_payload

    async def test_connection(self) -> tuple[bool, str]:
        return True, "ok"

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> list[list[float]]:
        self.embed_calls.append(texts)
        return [_keyword_vector(t, self.embed_dim) for t in texts]