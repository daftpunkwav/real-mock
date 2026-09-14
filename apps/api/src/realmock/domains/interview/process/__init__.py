"""Multi-round interview orchestration: process memory, round chain, and flow planning.

Single-round execution lives in :mod:`agents`; this package owns everything
that spans rounds: the process service (CRUD + round lifecycle), the shared
round memory/digest helpers, the agent flow planner (``planning``), and the
session catalog adapter.
"""
