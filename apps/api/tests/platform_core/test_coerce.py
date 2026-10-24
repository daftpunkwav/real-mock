"""Tests for realmock.platform.core.coerce (model-supplied number coercion).

Covers: the six shapes the rule must survive (plain number, numeric string,
None, non-numeric string, NaN, Infinity) plus the truncation/bool edge cases.
Conventions: deterministic asserts only; no fixtures needed.
"""

from __future__ import annotations

import math

from realmock.platform.core.coerce import coerce_int, try_coerce_int


def test_try_coerce_int_accepts_plain_number() -> None:
    assert try_coerce_int(42) == 42
    assert try_coerce_int(-5) == -5
    assert try_coerce_int(0) == 0
    # A float truncates toward zero, like int() itself.
    assert try_coerce_int(3.7) == 3
    assert try_coerce_int(-3.7) == -3


def test_try_coerce_int_accepts_numeric_string() -> None:
    assert try_coerce_int("42") == 42
    assert try_coerce_int("  7 ") == 7
    # A decimal string is not an int() candidate and degrades to None.
    assert try_coerce_int("88.7") is None


def test_try_coerce_int_accepts_bool() -> None:
    assert try_coerce_int(True) == 1
    assert try_coerce_int(False) == 0


def test_try_coerce_int_degrades_the_unusable_shapes() -> None:
    # None, a non-numeric string, NaN (ValueError) and Infinity (OverflowError)
    # all degrade to None instead of raising.
    assert try_coerce_int(None) is None
    assert try_coerce_int("next") is None
    assert try_coerce_int([]) is None
    assert try_coerce_int(float("nan")) is None
    assert try_coerce_int(float("inf")) is None
    assert try_coerce_int(float("-inf")) is None


def test_coerce_int_returns_default_for_unusable_shapes() -> None:
    default = 3
    for value in (None, "next", [], float("nan"), float("inf"), math.pi * 1e308):
        assert coerce_int(value, default) == default


def test_coerce_int_passes_convertible_values_through() -> None:
    assert coerce_int("9", 3) == 9
    assert coerce_int(0, 3) == 0
    assert coerce_int(12.9, 3) == 12
