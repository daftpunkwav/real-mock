# records/

Records domain: interview history and reports.

| Layer | Contents |
| --- | --- |
| `routes/history.py` | History endpoints (mounted at `/records`) |
| `routes/report.py` | Report endpoints (mounted at `/reports`) |
| `services/` | `report_store.py`, `report_events.py` (live report events), `debrief_runner.py`, `ingest.py`, `legacy_fallback.py` |
| [`agents/report/`](agents/report/README.md) | Report agent (two-stage ReAct pipeline) |
| `models/report.py` | Report tables |
| `column_migrations.py` | Column-level migrations |

Tests: `apps/api/tests/records/`.
