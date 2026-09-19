# profile/

Candidate profile domain. Single tenant: one profile row, PUT full-replace semantics.

| Layer | Contents |
| --- | --- |
| `routes/profile.py` | Profile read / update endpoints (mounted at `/profile`) |
| `services/store.py` | Persistence |
| `services/contract_guard.py` | Response contract guard |
| `schemas/` | `field_meta.py` (field metadata), `required.py`, `tech_domains.py`, `update.py` (PUT body), `response.py` |

Thin domain: no `models/`, `agents/`, or lifecycle hooks.

Tests: `apps/api/tests/profile/`.
