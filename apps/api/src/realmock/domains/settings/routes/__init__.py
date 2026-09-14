"""Handler configuration routes: three-stage configs in stages + model entries in models + connectivity tests in model_tests + third-party integrations."""

from realmock.domains.settings.routes.integrations import router as integrations_router
from realmock.domains.settings.routes.model_tests import router as model_tests_router
from realmock.domains.settings.routes.models import router as models_router
from realmock.domains.settings.routes.stages import router

__all__ = ["router", "models_router", "model_tests_router", "integrations_router"]
