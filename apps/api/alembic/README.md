# alembic/

Alembic migration chain for the api-domain database (`api.db`). Run from `apps/api/`: `alembic upgrade head`.

| Path | Purpose |
| --- | --- |
| `../alembic.ini` | Alembic config. Kept ASCII-only: alembic reads it with locale encoding, so non-ASCII comments break on GBK locales. The database URL is injected by `env.py`; no secrets here |
| `env.py` | Wires alembic to the app: database URL from `get_settings().api_database_url`, `target_metadata = ApiBase.metadata` |
| `script.py.mako` | Template for generated migration scripts |
| `versions/` | Ordered migration scripts (baseline column backfill, model-profile uniqueness, resume lineage, provider full-url / meta) |

## Scope

This chain manages only tables attached to `ApiBase` (profile / resume / settings domains, defined in `realmock.platform.models`). Session-domain tables on `SessionsBase` (prep / interview / records / growth, WS lease, rate-limit bucket) are not managed here: they are created at startup by `SessionsBase.metadata.create_all`, and column changes go through each domain's `column_migrations.py`, assembled by `realmock.bootstrap.sessions_orm`.
