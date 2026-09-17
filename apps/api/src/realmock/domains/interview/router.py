"""Mock interview service route aggregation.

Exposes ``service_router`` (routes only) for the aggregate entry point to include; standalone deployment is assembled by
``realmock.domains.interview.main:app (aggregate: realmock.asgi.create_app)``.
"""

from __future__ import annotations

from fastapi import APIRouter

from realmock.domains.interview.routes import options
from realmock.domains.interview.routes.brief import router as brief_router
from realmock.domains.interview.routes.interview import router as interview_router
from realmock.domains.interview.routes.ws import router as ws_router

service_router = APIRouter()
service_router.include_router(interview_router, prefix="/interview", tags=["interview"])
service_router.include_router(brief_router, prefix="/interview", tags=["interview"])
# reports moved to domains.records; growth moved to domains.growth
service_router.include_router(options.router, prefix="/options", tags=["options"])
service_router.include_router(ws_router, tags=["realtime"])
