"""Resume FastAPI router aggregation.

Mounts ``routes.router`` at prefix ``/resume``. The platform app factory
attaches this router under ``/api/v1`` with loopback / CSRF local-API guards;
this module does not declare auth itself.

Must not import persistence or Pydantic contracts — those live in services/ and schemas/.
"""

from __future__ import annotations

from fastapi import APIRouter

from realmock.domains.resume.routes.router import router as resume_router

service_router = APIRouter()
service_router.include_router(resume_router, prefix="/resume", tags=["resume"])
