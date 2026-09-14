"""Resume analysis prompt locale / output-rules unit tests."""

from __future__ import annotations

from realmock.domains.resume.schemas.limits import DIMENSION_KEYS
from realmock.domains.resume.services.analysis_prompt import (
    get_review_agent_prompt,
    language_instruction,
)
from realmock.platform.core.prompts import (
    AGENT_OUTPUT_RULES,
    with_agent_output_rules,
)


def test_language_instruction_zh_cn() -> None:
    text = language_instruction("zh-CN")
    assert "Simplified Chinese" in text or "zh-CN" in text
    assert "full-width" in text.lower() or "，。" in text


def test_language_instruction_en() -> None:
    text = language_instruction("en")
    assert "English" in text
    assert "half-width" in text.lower() or ", . ;" in text


def test_review_prompt_is_english_and_injects_locale() -> None:
    zh = get_review_agent_prompt("zh-CN")
    en = get_review_agent_prompt("en")
    assert "You are a senior hiring manager" in zh
    assert "You are a senior hiring manager" in en
    assert "Simplified Chinese" in zh or "zh-CN" in zh
    assert "review_set_plan step titles in English" in en
    assert "## Output constraints" in zh
    assert "review_set_plan" in zh
    assert "software engineer" in en.lower()


def test_review_prompt_contains_every_dimension_key() -> None:
    text = get_review_agent_prompt("en")
    for key in DIMENSION_KEYS:
        assert f'"{key}"' in text


def test_review_prompt_contains_score_rubric_not_llm_percentile() -> None:
    text = get_review_agent_prompt("en")
    assert "dimension rubric" in text
    assert "85" in text and "70" in text and "55" in text
    assert '"benchmark_percentile"' not in text


def test_review_prompt_plan_window_and_parallel_discipline() -> None:
    text = get_review_agent_prompt("zh-CN")
    assert "8-15" in text
    assert "in_progress" in text
    assert "mode=parallel" in text


def test_review_prompt_weight_rule_with_base_table() -> None:
    from realmock.domains.resume.schemas.limits import (
        DIMENSION_WEIGHTS,
        dimension_weight_range,
    )

    text = get_review_agent_prompt("en")
    assert "dimension_weights" in text
    for key in DIMENSION_KEYS:
        low, high = dimension_weight_range(key)
        base = DIMENSION_WEIGHTS[key]
        assert f"{key}: base {base:g} (allowed {low:g}-{high:g})" in text


def test_agent_output_rules_english_marker_idempotent() -> None:
    assert AGENT_OUTPUT_RULES.startswith("## Output constraints")
    once = with_agent_output_rules("Hello system")
    twice = with_agent_output_rules(once)
    assert once == twice
    assert once.count("## Output constraints") == 1
