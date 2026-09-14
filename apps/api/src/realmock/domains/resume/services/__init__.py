"""Resume domain service layer.

Callers import submodules (``store``, ``contract_guard``, ``analysis``)
rather than a barrel of functions so the HTTP layer stays explicit.

Must not import FastAPI routers.
"""
