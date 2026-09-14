"""Prep service (interview preparation coach) startup declarations.

Declares the prep session-domain for the composition root to register; the
bootstrap call itself lives in the entry points (``main`` / ``asgi``), never
in this package.
"""

from __future__ import annotations

# Session-domain ORM the composition root registers for standalone runs.
SESSION_DOMAINS: tuple[str, ...] = ("prep",)

__all__ = [
    "SESSION_DOMAINS",
]
