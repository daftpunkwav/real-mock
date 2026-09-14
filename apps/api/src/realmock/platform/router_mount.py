"""Aggregation entry route mounting: Unify /api/v1 and /api compatible aliases to avoid double copying of main."""

from __future__ import annotations

from collections.abc import Sequence

from fastapi import APIRouter, FastAPI

from realmock.platform.core.local_only import LOCAL_API_DEPENDENCIES


def include_service_routers(app: FastAPI, routers: Sequence[APIRouter], prefix: str) -> None:
    """Hang multiple service routers under the same API prefix (including local access control dependencies)."""
    for router in routers:
        app.include_router(router, prefix=prefix, dependencies=LOCAL_API_DEPENDENCIES)


def include_with_legacy_api_alias(
    app: FastAPI,
    routers: Sequence[APIRouter],
    *,
    versioned_prefix: str = "/api/v1",
    legacy_prefix: str = "/api",
) -> None:
    """Mount versioned prefixes and additionally register legacy prefixes (rolling compatibility period)."""
    include_service_routers(app, routers, versioned_prefix)
    legacy = APIRouter()
    for router in routers:
        legacy.include_router(router, prefix=legacy_prefix, dependencies=LOCAL_API_DEPENDENCIES)
    app.include_router(legacy)
