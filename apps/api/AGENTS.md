# apps/api agent rules

The run/layout reference lives in [README.md](README.md); the check-gate
table lives in [../../CONTRIBUTING.md](../../CONTRIBUTING.md). This file is
only the working rules for editing the backend.

## Layering is enforced, not aspirational

- `realmock.platform` must not import `realmock.domains` or
  `realmock.bootstrap` (AST guard:
  `tests/architecture/test_platform_no_domain_imports.py`).
- Domain packages must not import sibling domains — cross-domain wiring goes
  through `platform/contracts/` and the composition root in
  `bootstrap/` (`tests/architecture/test_domains_no_cross_imports.py`).
- `interview` and `prep` read shared profile/resume data only through the
  `candidate_read` facade (`platform/services/candidate_read.py`), never the
  `Resume`/`UserProfile` ORM models
  (`tests/architecture/test_db_boundary_imports.py`) — the domains run on
  separate databases.

When one of these tests fails, the change is wrong; do not weaken a guard to
pass it.

## Contract pipeline

Route or schema changes end with regenerating the contract:
`python scripts/export_openapi.py` (repo root), then `npm run
generate:api-types` from `apps/web`. `tests/architecture/
test_openapi_contract_sync.py` fails when the committed `openapi.json` is
stale. Pydantic docstrings leak into schema descriptions — document schemas
with `#` comments instead.

## Database

SQLite databases live in `platform/data/`. Schema changes go through Alembic
(`alembic/`); domains that backfill columns own a `column_migrations.py`.
`bootstrap/sessions_orm.py` registers ORM models per database so isolated
processes do not load unrelated business tables
(`tests/architecture/test_bootstrap_session_domains.py`).

## Runtime

Keep a single uvicorn worker locally: several caps (for example the resume
deep-review slot cap) are counted per process, so `--workers N` multiplies
them.

## Interview domain

`domains/interview` has additional enforced seams — see
[src/realmock/domains/interview/AGENTS.md](src/realmock/domains/interview/AGENTS.md).
