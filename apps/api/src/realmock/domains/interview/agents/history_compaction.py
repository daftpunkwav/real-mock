"""Adaptive fold thresholds for the pathological ephemeral compaction path.

Step-boundary compaction (:mod:`step_compaction`) owns history compression;
these ratios feed only the emergency per-call guard in
:mod:`prompt_assembler`, which never fires on a healthy 1M-window session.
"""

#: Window bands (tokens) for adaptive fold thresholds.
_SMALL_WINDOW_TOKENS = 16_000
_LARGE_WINDOW_TOKENS = 64_000


def adaptive_fold_thresholds(window: int) -> tuple[float, float]:
    """Ephemeral/persist fold ratios scaled to the context window.

    Small windows fill up fast (a fat system prompt alone can take a third
    of 8k), so both layers fold earlier; large windows can afford to lag and
    keep more verbatim history. Mid-band matches the historic 0.3/0.5.

    Returns:
        (ephemeral_ratio, persist_ratio) for ``compact_with_summary`` and
        the emergency per-call guard.
    """
    try:
        window = int(window)
    except (TypeError, ValueError):
        window = 0
    if window > 0 and window < _SMALL_WINDOW_TOKENS:
        return 0.25, 0.40
    if window >= _LARGE_WINDOW_TOKENS:
        return 0.40, 0.60
    return 0.30, 0.50


__all__ = ["adaptive_fold_thresholds"]
