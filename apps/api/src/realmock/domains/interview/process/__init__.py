"""Multi-round interview orchestration: process service, digest, and catalog.

Single-round execution lives in :mod:`agents`; this package owns everything
that spans rounds: the process service (CRUD + round lifecycle), the round
digest builder, and the session catalog adapter. Stored process documents
(plan / round-plan / memory / round chain) live in the neutral
:mod:`protocols` package shared with ``agents``.
"""
