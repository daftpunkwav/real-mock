# bootstrap/

Process bootstrap helpers (composition root): wiring that must know both platform and domains, so it cannot live in `platform/` — a platform → domain import is an architecture violation.

| Module | Purpose |
| --- | --- |
| `db_bootstrap.py` | Aggregated database bootstrap for the two-database layout; registers business ORM before table creation |
| `sessions_orm.py` | `sessions.db` domain registration: imports the selected session-domain models (prep / interview / records / growth) and assembles their column DDL before `create_all` |

`register_sessions_domain_models(domains=...)` controls which business packages register their ORM, so a domain started standalone does not load unrelated models.
