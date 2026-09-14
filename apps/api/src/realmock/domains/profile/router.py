"""Profile FastAPI router aggregation.

Mounts ``routes.profile`` at prefix ``/profile``. The platform app factory
attaches this router under ``/api/v1`` with loopback / CSRF local-API guards;
this module does not declare auth itself.

Must not import persistence or Pydantic contracts — those live in services/ and schemas/.
"""

from __future__ import annotations

from fastapi import APIRouter

from realmock.domains.profile.routes import profile

service_router = APIRouter()
service_router.include_router(profile.router, prefix="/profile", tags=["profile"])
