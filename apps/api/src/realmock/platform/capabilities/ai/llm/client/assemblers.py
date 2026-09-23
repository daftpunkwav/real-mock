"""Streaming tool-round incremental assembler: SSE events → (reasoning delta, content delta, fully assembled message).

There is one assembler each for openai_chat, anthropic_messages, and openai_responses; reasoning
deltas are returned immediately by ``feed`` and body-text deltas are additionally queued for
``drain_content`` (speculative streaming). Tool calls stay buffered until the stream ends, producing
a message with the same shape as non-streaming ``chat_message`` (``{"role": "assistant", "content",
"tool_calls"}``). Draining is side-effect free: ``message()`` assembles from its own buffers.

Every assembler also records terminal state: ``finish_reason`` (why generation stopped —
``length`` means the output cap cut the answer mid-stream) and ``terminal_error`` (a provider
error event arrived; the transport raises instead of silently ending). Anthropic thinking blocks
are additionally collected with their signatures so multi-turn tool loops can echo them back.
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
        self.finish_reason: str = ""
        self.terminal_error: str = ""
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
        choice = choices[0] if isinstance(choices[0], dict) else {}
        delta = choice.get("delta") or {}
        if not isinstance(delta, dict):
            return ""
        if choice.get("finish_reason"):
            self.finish_reason = str(choice["finish_reason"])
        reasoning = ""
        rc = delta.get("reasoning_content") or delta.get("reasoning") or ""
        if isinstance(rc, str) and rc:
            reasoning = rc
        content = delta.get("content")
        if isinstance(content, str) and content:
            self._content.append(content)
            self._pending_content.append(content)
        elif isinstance(delta.get("refusal"), str) and delta["refusal"]:
            # Provider refusal stream: surface as body text, never silently dropped.
            self._content.append(delta["refusal"])
            self._pending_content.append(delta["refusal"])
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
        if self.finish_reason:
            message["finish_reason"] = self.finish_reason
        return message


class _AnthropicRoundAssembler:
    """anthropic_messages stream events → (thinking deltas, drained text deltas, assembled message).

    thinking_delta is returned immediately by ``feed`` and text_delta is additionally queued for
    ``drain_content``; tool_use (input_json_delta fragments concatenated) buffers and assembles
    when the stream ends. Thinking blocks are collected with their ``signature`` deltas so the
    request builder can echo them back on tool-loop follow-ups (required by the official API
    whenever thinking is enabled). ``message_delta`` contributes ``stop_reason``; an ``error``
    event lands in ``terminal_error``.
    """

    def __init__(self) -> None:
        self._text: list[str] = []
        self._blocks: dict[int, dict[str, str]] = {}
        self._thinking: dict[int, dict[str, str]] = {}
        self.stop_reason: str = ""
        self.terminal_error: str = ""
        # Content deltas not yet drained by the transport (see _OpenAIRoundAssembler).
        self._pending_content: list[str] = []

    def drain_content(self) -> str:
        """Pop the content deltas accumulated since the last drain ("" when none)."""
        text = "".join(self._pending_content)
        self._pending_content.clear()
        return text

    def feed(self, event: dict[str, Any]) -> str:
        etype = event.get("type")
        if etype == "error":
            err = event.get("error") or {}
            message = err.get("message") if isinstance(err, dict) else None
            self.terminal_error = str(message or event)
            return ""
        if etype == "message_delta":
            self.stop_reason = str(event.get("delta", {}).get("stop_reason") or "")
            return ""
        if etype == "content_block_start":
            block = event.get("content_block") or {}
            btype = block.get("type")
            idx = int(event.get("index") or 0)
            if btype == "tool_use":
                self._blocks[idx] = {
                    "id": str(block.get("id") or ""),
                    "name": str(block.get("name") or ""),
                    "args": "",
                }
            elif btype == "thinking":
                self._thinking[idx] = {"thinking": "", "signature": ""}
            return ""
        if etype != "content_block_delta":
            return ""
        idx = int(event.get("index") or 0)
        delta = event.get("delta") or {}
        dtype = delta.get("type")
        if dtype == "thinking_delta":
            if idx in self._thinking:
                self._thinking[idx]["thinking"] += str(delta.get("thinking") or "")
            return str(delta.get("thinking") or "")
        if dtype == "signature_delta":
            if idx in self._thinking:
                self._thinking[idx]["signature"] += str(delta.get("signature") or "")
            return ""
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
        thinking_blocks = [
            self._thinking[idx]
            for idx in sorted(self._thinking)
            if self._thinking[idx]["thinking"] or self._thinking[idx]["signature"]
        ]
        if thinking_blocks:
            message["thinking_blocks"] = thinking_blocks
        if self.stop_reason:
            message["finish_reason"] = self.stop_reason
        return message


class _ResponsesRoundAssembler:
    """openai_responses stream events → (reasoning deltas, drained text deltas, assembled message).

    Reasoning-summary / reasoning-text deltas return immediately from ``feed``; output-text deltas
    additionally queue for ``drain_content``. Function calls buffer from ``output_item.added``
    (call_id/name) plus ``function_call_arguments.delta`` fragments. A ``response.completed``
    terminal snapshot is authoritative for ``message()`` (no delta-stitching drift); buffers are
    only the fallback when the gateway ends the stream without it. ``response.failed`` /
    ``response.incomplete`` / ``response.error`` land in ``terminal_error``; refusal deltas and
    server-side search items are surfaced instead of dropped.
    """

    def __init__(self) -> None:
        self._content: list[str] = []
        self._calls: dict[str, dict[str, str]] = {}
        self._call_order: list[str] = []
        self._pending_content: list[str] = []
        self._completed_response: dict[str, Any] | None = None
        self.finish_reason: str = ""
        self.terminal_error: str = ""
        self._server_tool_notes: list[str] = []

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
        if etype in ("response.failed", "response.incomplete"):
            response = event.get("response") or {}
            status = response.get("status") or etype.removeprefix("response.")
            details = response.get("incomplete_details") or {}
            err = response.get("error") or {}
            message = err.get("message") if isinstance(err, dict) else None
            suffix = details.get("reason") if isinstance(details, dict) else None
            self.finish_reason = (
                f"incomplete:{suffix}" if status == "incomplete" and suffix else str(status)
            )
            if status == "failed":
                self.terminal_error = str(
                    message or f"Provider reported failure (status=failed{', ' + str(suffix) if suffix else ''})"
                )
            return ""
        if etype == "error":
            err = event.get("error") or {}
            message = err.get("message") if isinstance(err, dict) else None
            self.terminal_error = str(message or event)
            return ""
        if etype == "response.output_text.delta":
            text = str(event.get("delta") or "")
            if text:
                self._content.append(text)
                self._pending_content.append(text)
            return ""
        if etype == "response.refusal.delta":
            text = str(event.get("delta") or "")
            if text:
                self._content.append(text)
                self._pending_content.append(text)
            return ""
        if etype in ("response.reasoning_summary_text.delta", "response.reasoning_text.delta"):
            return str(event.get("delta") or "")
        if etype == "response.output_item.added":
            item = event.get("item") or {}
            item_type = item.get("type")
            if item_type == "function_call":
                key = str(item.get("id") or item.get("call_id") or len(self._call_order))
                slot = self._call_slot(key)
                slot["id"] = str(item.get("call_id") or item.get("id") or slot["id"])
                slot["name"] = str(item.get("name") or slot["name"])
            elif item_type == "web_search_call":
                action = item.get("action") or {}
                query = action.get("query") if isinstance(action, dict) else None
                self._server_tool_notes.append(
                    f"[web_search] {query or '(provider-executed search)'}"
                )
            elif item_type == "file_search_call":
                results = item.get("results")
                count = len(results) if isinstance(results, list) else 0
                self._server_tool_notes.append(f"[file_search] {count} result(s)")
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
            from .response_extract import (
                extract_finish_reason,
                extract_server_tool_notes,
                extract_text,
                extract_tool_calls,
            )

            data = self._completed_response
            message: dict[str, Any] = {
                "role": "assistant",
                "content": extract_text(data, "openai_responses") or None,
            }
            tool_calls = extract_tool_calls(data, "openai_responses")
            if tool_calls:
                message["tool_calls"] = tool_calls
            finish = extract_finish_reason(data, "openai_responses")
            if finish and finish != "completed":
                message["finish_reason"] = finish
            self._server_tool_notes.extend(extract_server_tool_notes(data, "openai_responses"))
        else:
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
            if self.finish_reason:
                message["finish_reason"] = self.finish_reason
        if self._server_tool_notes:
            message["server_tool_notes"] = list(dict.fromkeys(self._server_tool_notes))
        return message


__all__ = ["_AnthropicRoundAssembler", "_OpenAIRoundAssembler", "_ResponsesRoundAssembler"]
