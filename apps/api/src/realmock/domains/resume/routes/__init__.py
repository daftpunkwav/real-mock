"""Resume HTTP route modules.

Import ``router`` from here only as a package path helper; the public
aggregator is ``realmock.domains.resume.router.service_router``.
"""

from realmock.domains.resume.routes.router import router

__all__ = ["router"]
