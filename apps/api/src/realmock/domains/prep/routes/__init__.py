"""Prep HTTP route modules.

The public aggregator is ``realmock.domains.prep.router.service_router``;
import route submodules (or ``routes.router``) directly. This package
deliberately does not re-export ``router`` so importing a submodule never
pulls the whole route graph through package init.
"""
