# realmock (package root)

The backend is a modular monolith: one FastAPI process, assembled here.

| Entry | Purpose |
| --- | --- |
| `asgi.py` | ASGI entry point; builds the app via the platform factory |
| [`bootstrap/`](bootstrap/README.md) | Process bootstrap: database wiring (`db_bootstrap.py`) and the session ORM (`sessions_orm.py`) |

## Structural rule

| Package | Owns | May depend on |
| --- | --- | --- |
| [`platform/`](platform/README.md) | Platform kernel: cross-domain infrastructure (AI / voice capabilities, DB, config, contracts, shared services) | `platform` only |
| [`domains/`](domains/README.md) | The seven business domains | `platform` + own package; never another domain |

Dependency direction is enforced by the test suite in `apps/api/tests/architecture/`: `test_platform_no_domain_imports.py` (platform must not import domains), `test_domains_no_cross_imports.py` (domains must not import each other), plus DB-boundary, layering, exposure and contract-sync guards. Cross-domain collaboration goes through platform services and contracts.
