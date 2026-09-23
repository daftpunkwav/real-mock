"""LLM response parsing: extract body / tool calls / reasoning, plus incremental parsing of SSE events.

Pure-function input (response JSON or a single SSE event) + protocol, producing a unified shape;
does not make network requests (see :mod:`streaming`).
"""

from __future__ import annotations

from typing import Any

from realmock.platform.core.constants import LLMProtocol

from .protocol_utils import _json_arguments


def extract_text(data: dict[str, Any], protocol: str) -> str:
    if protocol == LLMProtocol.ANTHROPIC_MESSAGES:
        content = data.get("content", [])
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                str(item.get("text") or "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            )
        return ""
    if protocol == LLMProtocol.OPENAI_RESPONSES:
        if isinstance(data.get("output_text"), str):
            return data["output_text"]
        for item in data.get("output", []) or []:
            if isinstance(item, dict) and item.get("type") == "message":
                content = item.get("content", [])
                if isinstance(content, list):
                    return "".join(c.get("text", "") for c in content if isinstance(c, dict))
                return str(content or "")
        return ""

    msg = data.get("choices", [{}])[0].get("message", {}) if data.get("choices") else {}
    content = msg.get("content")
    if isinstance(content, str) and content.strip():
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    for key in ("output_text", "reasoning_content", "reasoning"):
        val = msg.get(key)
        if isinstance(val, str) and val.strip():
            return val
    # Provider refused to answer: the refusal text is the user-visible body.
    refusal = msg.get("refusal")
    if isinstance(refusal, str) and refusal.strip():
        return refusal
    return ""


def extract_tool_calls(data: dict[str, Any], protocol: str) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    if protocol == LLMProtocol.ANTHROPIC_MESSAGES:
        for item in data.get("content", []) or []:
            if not isinstance(item, dict) or item.get("type") != "tool_use":
                continue
            calls.append(
                {
                    "id": item.get("id") or "",
                    "type": "function",
                    "function": {
                        "name": item.get("name") or "",
                        "arguments": _json_arguments(item.get("input")),
                    },
                }
            )
        return calls
    if protocol == LLMProtocol.OPENAI_RESPONSES:
        for item in data.get("output", []) or []:
            if not isinstance(item, dict) or item.get("type") != "function_call":
                continue
            calls.append(
                {
                    "id": item.get("call_id") or item.get("id") or "",
                    "type": "function",
                    "function": {
                        "name": item.get("name") or "",
                        "arguments": _json_arguments(item.get("arguments")),
                    },
                }
            )
        return calls
    choices = data.get("choices") or []
    if choices:
        return choices[0].get("message", {}).get("tool_calls") or []
    return calls


def extract_reasoning(data: dict[str, Any], protocol: str) -> str:
    """Extract reasoning text (or an empty string if absent).

    - anthropic_messages: concatenate ``thinking`` blocks in content;
    - openai_chat: the message's ``reasoning_content`` / ``reasoning``, with
      MiniMax's structured ``reasoning_details`` array as a fallback;
    - openai_responses: concatenate ``summary`` texts AND ``content[].reasoning_text``
      of reasoning output items (many gateways omit them; the empty string then
      signals "no reasoning").
    """
    if protocol == LLMProtocol.ANTHROPIC_MESSAGES:
        content = data.get("content", [])
        if isinstance(content, list):
            return "".join(
                str(item.get("thinking") or "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "thinking"
            )
        return ""
    if protocol == LLMProtocol.OPENAI_RESPONSES:
        parts: list[str] = []
        for item in data.get("output", []) or []:
            if not isinstance(item, dict) or item.get("type") != "reasoning":
                continue
            summary = item.get("summary")
            if isinstance(summary, list):
                parts.extend(
                    str(part.get("text") or "")
                    for part in summary
                    if isinstance(part, dict)
                )
            elif isinstance(summary, str):
                parts.append(summary)
            # Full reasoning content (the summary is often lossy); gateways that
            # only populate one of the two keep the other empty.
            content_items = item.get("content")
            if isinstance(content_items, list):
                parts.extend(
                    str(part.get("text") or part.get("reasoning_text") or "")
                    for part in content_items
                    if isinstance(part, dict)
                )
        return "".join(parts)
    msg = (data.get("choices") or [{}])[0].get("message", {}) if data.get("choices") else {}
    for key in ("reasoning_content", "reasoning"):
        val = msg.get(key)
        if isinstance(val, str) and val.strip():
            return val
    # MiniMax structured reasoning array: [{type: "reasoning", text: ...}, ...]
    details = msg.get("reasoning_details")
    if isinstance(details, list):
        parts = []
        for part in details:
            if isinstance(part, dict):
                text = part.get("text") or part.get("reasoning") or ""
                if isinstance(text, str) and text:
                    parts.append(text)
            elif isinstance(part, str) and part:
                parts.append(part)
        return "".join(parts)
    return ""


def extract_finish_reason(data: dict[str, Any], protocol: str) -> str:
    """Terminal reason of the response, "" when the protocol does not carry one.

    chat: ``finish_reason`` (stop/length/content_filter/tool_calls);
    anthropic: ``stop_reason`` (end_turn/max_tokens/tool_use/...);
    responses: ``status`` plus ``incomplete_details.reason`` ("completed",
    "incomplete:max_output_tokens", "failed").
    """
    if protocol == LLMProtocol.ANTHROPIC_MESSAGES:
        return str(data.get("stop_reason") or "")
    if protocol == LLMProtocol.OPENAI_RESPONSES:
        status = str(data.get("status") or "")
        if status == "incomplete":
            reason = (data.get("incomplete_details") or {}).get("reason")
            return f"incomplete:{reason}" if reason else "incomplete"
        return status
    choices = data.get("choices") or []
    if choices:
        return str(choices[0].get("finish_reason") or "")
    return ""


def extract_citations(data: dict[str, Any], protocol: str) -> list[dict[str, str]]:
    """URL citations attached to the answer (server-side search results).

    Only the responses protocol currently annotates messages
    (``output_text.annotations`` with ``url_citation`` entries).
    """
    citations: list[dict[str, str]] = []
    if protocol != LLMProtocol.OPENAI_RESPONSES:
        return citations
    for item in data.get("output", []) or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            for ann in part.get("annotations") or []:
                if not isinstance(ann, dict):
                    continue
                url = str(ann.get("url") or "")
                if not url:
                    continue
                citations.append(
                    {"url": url, "title": str(ann.get("title") or "")}
                )
    return citations


def extract_server_tool_notes(data: dict[str, Any], protocol: str) -> list[str]:
    """Human-readable lines for server-executed tool items (native web search etc.).

    These output items never become client tool calls; without this they would
    silently vanish. Returns one line per item, empty when none.
    """
    notes: list[str] = []
    if protocol != LLMProtocol.OPENAI_RESPONSES:
        return notes
    for item in data.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "web_search_call":
            action = item.get("action") or {}
            query = action.get("query") if isinstance(action, dict) else None
            notes.append(f"[web_search] {query or '(provider-executed search)'}")
        elif item_type == "file_search_call":
            results = item.get("results")
            count = len(results) if isinstance(results, list) else 0
            notes.append(f"[file_search] {count} result(s)")
    return notes


def provider_business_error(data: dict[str, Any], protocol: str) -> str:
    """Business-level failure inside an HTTP-success body, "" when healthy.

    Covers MiniMax's ``base_resp.status_code/status_msg`` (HTTP 200 + error is
    a documented MiniMax pattern) and Responses ``status=failed``.
    """
    if protocol == LLMProtocol.OPENAI_RESPONSES:
        status = str(data.get("status") or "")
        if status == "failed":
            err = data.get("error") or {}
            code = err.get("code") if isinstance(err, dict) else None
            message = err.get("message") if isinstance(err, dict) else None
            return f"Provider reported failure (status=failed, code={code}): {message or 'no detail'}"
        return ""
    base_resp = data.get("base_resp")
    if isinstance(base_resp, dict):
        code = base_resp.get("status_code")
        # 0 means success in the MiniMax base_resp convention.
        if code not in (None, 0, "0"):
            return f"Provider business error (base_resp.status_code={code}): {base_resp.get('status_msg') or 'no detail'}"
    return ""


def parse_sse_event(event: dict[str, Any], protocol: str) -> tuple[str, str]:
    """Extracted from a single SSE event (body delta, think delta); unrecognized events returned ("", "")."""
    if protocol == LLMProtocol.ANTHROPIC_MESSAGES:
        if event.get("type") == "content_block_delta":
            delta = event.get("delta") or {}
            if delta.get("type") == "thinking_delta":
                return "", str(delta.get("thinking") or "")
            return str(delta.get("text") or ""), ""
        return "", ""
    if protocol == LLMProtocol.OPENAI_RESPONSES:
        if event.get("type") == "response.output_text.delta":
            return str(event.get("delta") or ""), ""
        if event.get("type") in ("response.reasoning_summary_text.delta", "response.reasoning_text.delta"):
            return "", str(event.get("delta") or "")
        return "", ""
    # openai_chat
    choices = event.get("choices") or []
    if not choices:
        return "", ""
    delta = choices[0].get("delta") or {}
    if not isinstance(delta, dict):
        return "", ""
    token = str(delta.get("content") or "")
    reasoning = str(delta.get("reasoning_content") or delta.get("reasoning") or "")
    return token, reasoning


__all__ = [
    "extract_citations",
    "extract_finish_reason",
    "extract_reasoning",
    "extract_server_tool_notes",
    "extract_text",
    "extract_tool_calls",
    "parse_sse_event",
    "provider_business_error",
]
