"""Profile domain: single-tenant candidate profile HTTP API.

HTTP surface for the sole ``UserProfile`` row in api.db:
GET (read / get-or-create), PUT (full update), POST-clear (blank fields).
Interview and Prep must read that row through ``platform.services.candidate_read``,
not by importing this package.

Public mount: ``router.service_router`` under ``/profile``.
"""
