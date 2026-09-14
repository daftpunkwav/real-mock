"""Profile domain service layer.

Callers import submodules (``contract_guard``, ``store``) rather than a barrel
of functions so the HTTP layer stays explicit about which side it uses.

Must not import FastAPI routers.
"""
