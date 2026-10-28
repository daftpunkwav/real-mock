"""Coercion of model-supplied values into usable integers.

A model-supplied number arrives as JSON, so it can be a plain number, a
numeric string, null, a non-numeric string, NaN or Infinity (``json.loads``
accepts the last two). One home owns the rule "a value that cannot be
converted degrades to the fallback": ``int(float("inf"))`` raises
``OverflowError``, which is not a ``ValueError``, so a call site that writes
its own ``except (TypeError, ValueError)`` turns a malformed model answer
into a raised error. Every coercion site keeps its own bounds/clamp; only
the conversion rule lives here.
"""

from __future__ import annotations

from typing import Any

__all__ = ["coerce_int", "try_coerce_int"]


def try_coerce_int(value: Any, *, via_float: bool = False) -> int | None:
    """Coerce one model-supplied value to int, or None when not convertible.

    ``None``, a non-numeric string, NaN (``ValueError``) and Infinity
    (``OverflowError``) all degrade to None. Booleans convert (``True`` ->
    ``1``) and a float truncates toward zero, like ``int()`` itself; a
    numeric string with a decimal point (``"88.7"``) is not an ``int()``
    candidate and degrades to None.

    With ``via_float`` the value converts through ``float`` first, so a
    decimal string truncates like the float it names (``"88.7"`` -> ``88``)
    and a value beyond the float range (``10**400``, Infinity) degrades to
    None instead of surviving as a huge integer.
    """
    try:
        return int(float(value)) if via_float else int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def coerce_int(value: Any, default: int, *, via_float: bool = False) -> int:
    """Coerce one model-supplied value to int; ``default`` when not convertible."""
    converted = try_coerce_int(value, via_float=via_float)
    return default if converted is None else converted
