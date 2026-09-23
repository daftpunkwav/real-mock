"""Streaming tool-round incremental assembler: SSE events → (reasoning delta, content delta, fully assembled message).

There is one assembler each for openai_chat and anthropic_messages; reasoning deltas are returned
immediately by ``feed`` and body-text deltas are additionally queued for ``drain_content``
(speculative streaming). Tool calls stay buffered until the stream ends, producing a message with
the same shape as non-streaming ``chat_message`` (``{"role": "assistant", "content", "tool_calls"}``).
Draining is side-effect free: ``message()`` assembles from its own buffers.
"""

from __future__ import annotations

from typing import Any


class _OpenAIRoundAssembler:
    """openai_chat streaming deltas → (reasoning deltas, drained content deltas, assembled message).

    ``feed`` returns reasoning immediately and queues content deltas for ``drain_content``;
    tool_calls (id/name/arguments fragments concatenated by index) buffer until the stream
    ends, then assemble into a message matching the non-streaming ``chat_message`` shape.
    """

    def __init__(self) -> None:
        self._content: list[str] = []
        self._calls: dict[int, dict[str, Any]] = {}
        # Content deltas not yet drained by the transport (speculative streaming);
        # ``message()`` keeps buffering independently, so draining is side-effect free.
        self._pending_content: list[str] = []

    def drain_content(self) -> str:
        """Pop the content deltas accumulated since the last drain ("" when none)."""
        text = "".join(self._pending_content)
        self._pending_content.clear()
        return text

    def feed(self, event: dict[str, Any]) -> str:
        choices = event.get("choices") or []
        if not choices:
            return ""
        delta = choices[0].get("delta") or {}
        if not isinstance(delta, dict):
            return ""
        reasoning = ""
        rc = delta.get("reasoning_content") or delta.get("reasoning") or ""
        if isinstance(rc, str) and rc:
            reasoning = rc
        content = delta.get("content")
        if isinstance(content, str) and content:
            self._content.append(content)
            self._pending_content.append(content)
        for tc in delta.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            idx = int(tc.get("index") or 0)
            slot = self._calls.setdefault(
                idx, {"id": "", "function": {"name": "", "arguments": ""}}
            )
            if tc.get("id"):
                slot["id"] = str(tc["id"])
            fn = tc.get("function") or {}
            if fn.get("name"):
                slot["function"]["name"] += str(fn["name"])
            if fn.get("arguments"):
                slot["function"]["arguments"] += str(fn["arguments"])
        return reasoning

    def message(self) -> dict[str, Any]:
        tool_calls = [
            {
                "id": self._calls[idx]["id"] or f"call_{idx}",
                "type": "function",
                "function": self._calls[idx]["function"],
            }
            for idx in sorted(self._calls)
        ]
        message: dict[str, Any] = {"role": "assistant", "content": "".join(self._content) or None}
        if tool_calls:
            message["tool_calls"] = tool_calls
        return message


class _AnthropicRoundAssembler:
    """anthropic_messages stream events → (thinking deltas, drained text deltas, assembled message).

    thinking_delta is returned immediately by ``feed`` and text_delta is additionally queued for
    ``drain_content``; tool_use (input_json_delta fragments concatenated) buffers and assembles
    when the stream ends. Signature blocks (signature_delta) are not exposed.
    """

    def __init__(self) -> None:
        self._text: list[str] = []
        self._blocks: dict[int, dict[str, str]] = {}
        # Content deltas not yet drained by the transport (see _OpenAIRoundAssembler).
        self._pending_content: list[str] = []

    def drain_content(self) -> str:
        """Pop the content deltas accumulated since the last drain ("" when none)."""
        text = "".join(self._pending_content)
        self._pending_content.clear()
        return text

    def feed(self, event: dict[str, Any]) -> str:
        etype = event.get("type")
        if etype == "content_block_start":
            block = event.get("content_block") or {}
            if block.get("type") == "tool_use":
                idx = int(event.get("index") or 0)
                self._blocks[idx] = {
                    "id": str(block.get("id") or ""),
                    "name": str(block.get("name") or ""),
                    "args": "",
                }
            return ""
        if etype != "content_block_delta":
            return ""
        idx = int(event.get("index") or 0)
        delta = event.get("delta") or {}
        dtype = delta.get("type")
        if dtype == "thinking_delta":
            return str(delta.get("thinking") or "")
        if dtype == "text_delta":
            text = str(delta.get("text") or "")
            self._text.append(text)
            self._pending_content.append(text)
        elif dtype == "input_json_delta":
            if idx in self._blocks:
                self._blocks[idx]["args"] += str(delta.get("partial_json") or "")
        return ""

    def message(self) -> dict[str, Any]:
        tool_calls = [
            {
                "id": self._blocks[idx]["id"] or f"call_{idx}",
                "type": "function",
                "function": {
                    "name": self._blocks[idx]["name"],
                    "arguments": self._blocks[idx]["args"] or "{}",
                },
            }
            for idx in sorted(self._blocks)
        ]
        message: dict[str, Any] = {"role": "assistant", "content": "".join(self._text) or None}
        if tool_calls:
            message["tool_calls"] = tool_calls
        return message


class _ResponsesRoundAssembler:
    """openai_responses stream events → (reasoning deltas, drained text deltas, assembled message).

    Reasoning-summary / reasoning-text deltas return immediately from ``feed``; output-text deltas
    additionally queue for ``drain_content``. Function calls buffer from ``output_item.added``
    (call_id/name) plus ``function_call_arguments.delta`` fragments. A ``response.completed``
    terminal snapshot is authoritative for ``message()`` (no delta-stitching drift); buffers are
    only the fallback when the gateway ends the stream without it.
    """

    def __init__(self) -> None:
        self._content: list[str] = []
        self._calls: dict[str, dict[str, str]] = {}
        self._call_order: list[str] = []
        self._pending_content: list[str] = []
        self._completed_response: dict[str, Any] | None = None

    def drain_content(self) -> str:
        """Pop the content deltas accumulated since the last drain ("" when none)."""
        text = "".join(self._pending_content)
        self._pending_content.clear()
        return text

    def _call_slot(self, key: str) -> dict[str, str]:
        if key not in self._calls:
            self._calls[key] = {"id": "", "name": "", "args": ""}
            self._call_order.append(key)
        return self._calls[key]

    def feed(self, event: dict[str, Any]) -> str:
        etype = event.get("type")
        if etype == "response.output_text.delta":
            text = str(event.get("delta") or "")
            if text:
                self._content.append(text)
                self._pending_content.append(text)
            return ""
        if etype in ("response.reasoning_summary_text.delta", "response.reasoning_text.delta"):
            return str(event.get("delta") or "")
        if etype == "response.output_item.added":
            item = event.get("item") or {}
            if item.get("type") == "function_call":
                key = str(item.get("id") or item.get("call_id") or len(self._call_order))
                slot = self._call_slot(key)
                slot["id"] = str(item.get("call_id") or item.get("id") or slot["id"])
                slot["name"] = str(item.get("name") or slot["name"])
            return ""
        if etype == "response.function_call_arguments.delta":
            key = str(event.get("item_id") or "")
            if key in self._calls:
                self._calls[key]["args"] += str(event.get("delta") or "")
            return ""
        if etype == "response.completed":
            response = event.get("response")
            if isinstance(response, dict):
                self._completed_response = response
            return ""
        return ""

    def message(self) -> dict[str, Any]:
        if self._completed_response is not None:
            from .response_extract import extract_text, extract_tool_calls

            data = self._completed_response
            message: dict[str, Any] = {
                "role": "assistant",
                "content": extract_text(data, "openai_responses") or None,
            }
            tool_calls = extract_tool_calls(data, "openai_responses")
            if tool_calls:
                message["tool_calls"] = tool_calls
            return message
        tool_calls = [
            {
                "id": self._calls[key]["id"] or f"call_{idx}",
                "type": "function",
                "function": {
                    "name": self._calls[key]["name"],
                    "arguments": self._calls[key]["args"] or "{}",
                },
            }
            for idx, key in enumerate(sorted(self._call_order))
        ]
        message = {"role": "assistant", "content": "".join(self._content) or None}
        if tool_calls:
            message["tool_calls"] = tool_calls
        return message


__all__ = ["_AnthropicRoundAssembler", "_OpenAIRoundAssembler", "_ResponsesRoundAssembler"]

