"""Tests for realmock.platform.capabilities.ai.llm.defaults (token budgets).

Covers: user-configured values pass through, missing/non-positive values fall
back to the platform constants, and a non-finite value degrades to the
fallback instead of raising (``json.loads`` accepts ``Infinity``, and
``int(float('inf'))`` raises ``OverflowError``).
Conventions: deterministic asserts only; no fixtures needed.
"""

from realmock.platform.capabilities.ai.llm import defaults


def test_resolvers_pass_configured_values_through() -> None:
    assert defaults.resolve_context_window(128_000) == 128_000
    assert defaults.resolve_max_output_tokens(4_096) == 4_096


def test_resolvers_fall_back_on_missing_or_nonpositive_values() -> None:
    assert defaults.resolve_context_window(None) == defaults.DEFAULT_CONTEXT_WINDOW
    assert defaults.resolve_context_window(0) == defaults.DEFAULT_CONTEXT_WINDOW
    assert defaults.resolve_context_window(-5) == defaults.DEFAULT_CONTEXT_WINDOW
    assert defaults.resolve_max_output_tokens(None) == defaults.DEFAULT_MAX_OUTPUT_TOKENS
    assert defaults.resolve_max_output_tokens(0) == defaults.DEFAULT_MAX_OUTPUT_TOKENS


def test_resolvers_degrade_non_finite_values() -> None:
    assert defaults.resolve_context_window(float("inf")) == defaults.DEFAULT_CONTEXT_WINDOW
    assert defaults.resolve_context_window(float("nan")) == defaults.DEFAULT_CONTEXT_WINDOW
    assert defaults.resolve_max_output_tokens(float("inf")) == defaults.DEFAULT_MAX_OUTPUT_TOKENS
    assert defaults.resolve_max_output_tokens(float("nan")) == defaults.DEFAULT_MAX_OUTPUT_TOKENS
