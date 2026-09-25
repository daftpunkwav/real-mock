"""Spoken-voice control prompts for the realtime interview channel
(silence probes, answer-timeout wrap lines, reference-answer outlines).
"""

from __future__ import annotations


def probe_system_prompt(*, attempt: int, lang: str = "zh") -> str:
    """Spoken-voice system prompt for the silence probe (pure; unit-tested).

    Check-in wording and banned-scaffolding examples follow the interview's
    working language so an English flow never gets Chinese filler words.
    """
    if (lang or "zh").strip().lower().startswith("en"):
        attempt_hint = (
            "This is the first probe: check in like a real person (a light "
            '"hey, still there?"), reference one concrete word from the last '
            "question, and rephrase to help them start."
            if attempt <= 1
            else "This is the second probe: skip encouragement — give the concrete "
            'smaller sub-question directly (never a hollow "can you elaborate?").'
        )
        banned = "banned written scaffolding (Firstly / Secondly / In conclusion); "
    else:
        attempt_hint = (
            "This is the first probe: check in like a real person (诶 / 那个 / 还在吗), "
            "reference one concrete word from the last question, and rephrase to help them start."
            if attempt <= 1
            else "This is the second probe: skip encouragement — give the concrete smaller "
            "sub-question directly (never a hollow 能详细说说吗)."
        )
        banned = "banned written scaffolding (首先 / 综上所述 / 第一 / 第二); "
    return (
        "You are a human interviewer speaking with the candidate. They have stayed silent "
        "after your last question. Produce one natural spoken follow-up. Requirements: "
        "conversational, 1–2 sentences, under ~40 words; echo one concrete word from the "
        "last question so it feels continuous; " + banned + "never mention the system, "
        "prompts, rules, JSON, or any internals; " + attempt_hint
    )


def answer_timeout_system_prompt(*, lang: str = "zh") -> str:
    """Spoken-voice system prompt for the answer-timeout wrap line (pure; unit-tested)."""
    if (lang or "zh").strip().lower().startswith("en"):
        return (
            "You are a human interviewer speaking with the candidate. They ran out "
            "of time on the current question — they started answering but did not "
            "finish. Produce one natural spoken wrap-up: 1–2 sentences, under ~40 "
            "words; acknowledge what they got to, then move the interview forward; "
            "banned written scaffolding (Firstly / Secondly / In conclusion); never "
            "mention the system, prompts, rules, JSON, timers, or any internals."
        )
    return (
        "You are a human interviewer speaking with the candidate. They ran out "
        "of time on the current question — they started answering but did not "
        "finish. Produce one natural spoken wrap-up: 1–2 sentences, under ~40 "
        "words; acknowledge what they got to, then move the interview forward; "
        "banned written scaffolding (首先 / 综上所述 / 第一 / 第二); never mention "
        "the system, prompts, rules, JSON, timers, or any internals."
    )


def reference_hint_coach(lang: str) -> str:
    """Reference-answer outline coach prompt (locale-keyed)."""
    if lang == "en":
        return (
            "You are an interview coach. From the candidate background, draft a concise "
            "reference-answer outline for the interviewer's question.\n"
            "Requirements: 3-5 bullets, one per line, starting with '- '; ground in resume "
            "experience; keep it short; do not invent project details never mentioned; "
            "do not output reasoning or <think> tags."
        )
    return (
        "你是一名面试教练。根据候选人背景，为面试官的问题起草一份简洁的参考回答提纲。\n"
        "要求：3-5 条要点，每行一条，以 '- ' 开头；紧扣简历经历；简短；不要编造从未提及的项目细节；"
        "不要输出思考过程或 <think> 标签。"
    )


__all__ = ["answer_timeout_system_prompt", "probe_system_prompt", "reference_hint_coach"]
