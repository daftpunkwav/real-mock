# growth/

Growth domain: statistics derived from interview history (aggregated stats, insights).

| Layer | Contents |
| --- | --- |
| `routes/router.py` | Growth HTTP API (history, insights, aggregated stats; mounted at `/growth`) |
| `services/` | `ingest.py`, `learning.py`, `persist_from_summary.py` |
| `agents/growth.py` | Growth agent |
| `models/growth.py` | Growth tables |
| `column_migrations.py` | Column-level migrations |

Tests: `apps/api/tests/growth/`.
