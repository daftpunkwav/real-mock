# domains/ agent rules

The domain table lives in [README.md](README.md). This file is the working
rules shared by all domains.

## Boundaries

- Domains must not import sibling domains — AST guard:
  `tests/architecture/test_domains_no_cross_imports.py`.
- Cross-domain reactions go through `platform/contracts/` events; reads of
  profile/resume data from agent domains go through
  `platform/services/candidate_read.py`. Wire new edges there, not with
  direct imports.
- Domain tests live in `apps/api/tests/<domain>/`, not inside `src/`.

## Internal shape

Each domain keeps the same layers: `routes/` (HTTP), `schemas/` (pydantic
request/response), `services/`, `agents/` (LLM roles, where present),
`models/` (ORM). New code goes in the matching layer rather than introducing
a new top-level concept.

## Adding a domain

Register routers via `platform/router_mount.py`; ORM models are registered
per database by `bootstrap/sessions_orm.py` so isolated processes do not load
unrelated business tables.

## Interview domain

`interview/` carries additional enforced seams (agents facade, process seam,
realtime wiring) — see [interview/AGENTS.md](interview/AGENTS.md).
