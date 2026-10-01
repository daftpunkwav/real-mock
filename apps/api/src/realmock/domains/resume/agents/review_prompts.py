"""Review-facing and user-facing copy blocks of the resume-review agent.

Single home for every text the review agent emits outside its final payload:
post-loop finalize phase notices (forced final / self-correction / repair),
tool-budget and circuit-breaker refusal observations, and the text-only
degradation notice for PDF reviews without page images. Pure text builders,
no I/O; orchestration lives in ``review.py``, the JSON finalize chain in
``review_json.py``.
"""

from __future__ import annotations

import json

from realmock.platform.capabilities.ai.agent import OnAgentEvent, emit_agent_event

# User-visible progress notices for the post-loop finalize phases (rendered as
# timeline rows by the web UI) so a slow synthesis never looks like a hang.
_FINALIZE_NOTICES: dict[str, tuple[str, str]] = {
    "forced_final": (
        "正在基于已收集的证据汇总生成最终评价…",
        "Synthesizing the final evaluation from the gathered evidence…",
    ),
    "self_correction": (
        "上一轮输出不是有效 JSON，正在重新输出…",
        "The previous output was not valid JSON; re-emitting it…",
    ),
    "repair": (
        "正在基于已收集的证据重建评价 JSON…",
        "Rebuilding the evaluation JSON from the gathered evidence…",
    ),
}


async def _emit_finalize_notice(
    on_event: OnAgentEvent | None,
    locale: str,
    kind: str,
) -> None:
    zh, en = _FINALIZE_NOTICES[kind]
    await emit_agent_event(on_event, {"type": "notice", "message": en if locale == "en" else zh})


# User-facing reasons when a PDF review runs without page images. The notice
# is explicit degradation, never a silent text-only fallback.
_VISUAL_UNAVAILABLE_REASONS: dict[str, tuple[str, str]] = {
    "no_vision": (
        "模型未启用图片输入，本次按纯文本评审；版式/字体结论仅供参考",
        "Vision input is disabled; text-only review — layout/typeface findings are approximate",
    ),
    "missing_file": (
        "原始 PDF 文件缺失，本次按纯文本评审",
        "Original PDF is missing; text-only review",
    ),
    "render_failed": (
        "PDF 页面渲染失败，本次按纯文本评审",
        "PDF page rendering failed; text-only review",
    ),
    "filtered": (
        "页面图超出模型上下文被过滤，本次按纯文本评审",
        "Page images were dropped by the context budget; text-only review",
    ),
}


def _vision_notice_message(*, locale: str, file_type: str, visual_status: str) -> str | None:
    """Notice text when a PDF review runs without page images; None otherwise."""
    if file_type.lower() != "pdf" or visual_status == "ok":
        return None
    reason = _VISUAL_UNAVAILABLE_REASONS.get(visual_status)
    if reason is None:
        return None
    zh_reason, en_reason = reason
    return en_reason if locale == "en" else zh_reason


def _budget_refusal_text(name: str, limit: int) -> str:
    return json.dumps(
        {
            "error": "tool_budget_exhausted",
            "tool": name,
            "message": (
                f"Tool-call budget exhausted ({limit} calls). "
                "Write the final answer with the evidence already gathered."
            ),
        },
        ensure_ascii=False,
    )


def _circuit_refusal_text(name: str, streak: int) -> str:
    return json.dumps(
        {
            "error": "circuit_open",
            "tool": name,
            "message": (
                f"This exact call ({name} with the same arguments) failed "
                f"{streak} times in a row and is temporarily blocked. Change the "
                "arguments, use a different tool, or move on to writing the "
                "final answer."
            ),
        },
        ensure_ascii=False,
    )
