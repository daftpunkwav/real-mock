"""Stored process protocols shared across layers: flow plans, round programs,
process memory documents, and the round chain.

Pure document/stepping logic only (no DB, no LLM): ``process`` owns
persistence and lifecycle; ``agents`` and ``routes`` read these protocols to
drive and prompt the interview. Neither layer imports the other's internals
through here.
"""
