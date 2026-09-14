"""Structured follow-up signal analyzer.

Without calling an LLM, rules determine whether a candidate's answer needs a follow-up and the issue category,
then generate a one-sentence follow-up cue and inject it into the system prompt to guide the interviewer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from realmock.domains.interview.constants import FollowupCategory


# Vague fillers (Chinese colloquial + common English hedges) for bilingual answers
VAGUE_TERMS: tuple[str, ...] = (
    # zh-CN
    "大概", "可能", "或许", "也许", "差不多", "一般般", "还行", "还可以",
    "还行吧", "基本上", "大致", "印象中", "感觉", "好像", "大概吧",
    # en
    "maybe", "perhaps", "probably", "roughly", "basically", "kinda", "sort of",
    "I guess", "not sure", "about it", "more or less",
)

# Quantitative cues: digits/percents, metric acronyms, and Chinese duration units.
# Short Latin units use word boundaries so bare "s" does not match every English sentence.
HAS_QUANT_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?%?)"
    r"|\b(QPS|RPS|TPS|RT|DAU|MAU|UV|PV|GB|MB|KB|ms|s)\b"
    r"|(分钟|小时|天|周|月|年)",
    re.IGNORECASE,
)

# Non-investigation phases: in these phases the missing_data / tech_hole rules do not apply.
# reverse_qa is candidate-asks + summary is wrap-up; no quantitative data is required there.
_NON_TECHNICAL_PHASES: frozenset[str] = frozenset({
    "identity_check", "self_intro", "reverse_qa", "summary",
})


@dataclass(frozen=True)
class FollowupSignal:
    """Structured follow-up decision injected into the system prompt."""

    needs_followup: bool
    category: FollowupCategory
    suggested_probe: str  # Cue injected into the system prompt


_NO_SIGNAL = FollowupSignal(False, FollowupCategory.NONE, "")


def analyze(
    answer: str,
    question: str = "",
    tech_domains: list[str] | None = None,
    *,
    phase_id: str = "",
) -> FollowupSignal:
    """Determine a follow-up signal from the answer content, current question, and candidate's tech stack.

    Priority: vague > off_topic > missing_data > tech_hole.

    Args:
        phase_id: ID of the current interview phase. During candidate-questions/summary/small-talk phases, technical follow-up rules
            (missing_data / tech_hole) are skipped to avoid inappropriate guidance such as
            asking the candidate to "provide quantified data" during their question period. vague / off_topic
            remain active because ambiguity or digression merits guidance in any phase.
    """
    text = (answer or "").strip()
    if not text:
        return FollowupSignal(
            True, FollowupCategory.MISSING_DATA, "The candidate gave no substance; guide them to elaborate."
        )

    # Tech rules only in assessment phases; skip reverse_qa / summary / chill
    skip_tech_rules = phase_id in _NON_TECHNICAL_PHASES

    # 0. vague before off_topic — vague wording is itself a probe signal
    lower = text.lower()
    vague_hits = sum(1 for term in VAGUE_TERMS if term.lower() in lower)
    if vague_hits >= 2:
        return FollowupSignal(
            True,
            FollowupCategory.VAGUE,
            "The candidate used several vague phrases; ask for concrete numbers, scale, or time ranges.",
        )
    if vague_hits == 1 and len(text) < 60:
        return FollowupSignal(
            True,
            FollowupCategory.VAGUE,
            "The answer is short and vague; ask for a concrete example with quantified impact.",
        )

    # 1. off_topic: very short answer with no keyword overlap
    if question and len(text) < 30:
        q_keywords = _question_keywords(question)
        if q_keywords and not _answer_contains_any(text, q_keywords):
            return FollowupSignal(
                True,
                FollowupCategory.OFF_TOPIC,
                "The answer drifted off topic; politely steer back and probe the core point.",
            )

    # Remaining tech rules skipped in reverse_qa / summary / etc.
    if skip_tech_rules:
        return _NO_SIGNAL

    # 2. missing_data: longer answer with no quantified metrics
    if len(text) >= 40 and not HAS_QUANT_PATTERN.search(text):
        return FollowupSignal(
            True,
            FollowupCategory.MISSING_DATA,
            "The description is rich but lacks numbers; probe QPS/latency/improvement ratio/user scale.",
        )

    # 3. tech_hole: little overlap with declared tech domains
    if tech_domains:
        domains = [d.strip() for d in tech_domains if d.strip()]
        if domains and not _matches_any_domain(text, domains):
            return FollowupSignal(
                True,
                FollowupCategory.TECH_HOLE,
                (
                    "The answer does not reflect declared tech domains ({domains}); "
                    "guide them to connect those technologies or probe the related concepts."
                ).format(domains=", ".join(domains[:5])),
            )

    return _NO_SIGNAL


# ---------------------------------------------------------------------------
# Auxiliary
# ---------------------------------------------------------------------------


def _question_keywords(question: str) -> list[str]:
    """Extract question keywords: Chinese 2-grams + English/numeric tokens.

    Used for off_topic substring matching; retain stop words to avoid over-filtering.
    """
    keywords: list[str] = []
    # English/numeric token
    for m in re.finditer(r"[A-Za-z]+|\d+", question):
        keywords.append(m.group(0).lower())
    # Chinese: Strip ASCII, whitespace, common punctuation
    chinese = re.sub(
        r"[A-Za-z0-9\s\u3000-\u303f\uff00-\uffef\u2000-\u206f!-/:-@[-`{-~]",
        "",
        question,
    )
    if len(chinese) >= 2:
        for i in range(len(chinese) - 1):
            keywords.append(chinese[i:i + 2])
    return keywords


def _answer_contains_any(answer: str, keywords: list[str]) -> bool:
    """Determine whether answer contains any keyword (substring matching)."""
    if not keywords:
        return True
    return any(kw in answer for kw in keywords)


def _matches_any_domain(text: str, domains: list[str]) -> bool:
    """Determine whether the text contains keywords in any technical field."""
    lower = text.lower()
    return any(d.lower() in lower for d in domains)


__all__ = [
    "FollowupCategory",
    "FollowupSignal",
    "analyze",
]