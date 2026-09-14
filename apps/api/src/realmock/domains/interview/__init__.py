"""Mock-interview domain: LLM execution chain, realtime room, and multi-round orchestration.

Layers (dependency flows downward only):
``routes`` (HTTP/WS entry) → ``process`` (multi-round orchestration) →
``realtime`` (WS turn state machine + media pipeline) → ``agents`` (LLM
execution chain). ``capabilities`` (perception plugins), ``ledger``
(per-turn record), ``models``/``schemas`` serve all layers. Layering is
held by ``tests/architecture/test_interview_layering.py``.
"""
