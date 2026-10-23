# records/

Records domain: interview history and reports.

| Layer | Contents |
| --- | --- |
| `routes/history.py` | History endpoints (mounted at `/records`) |
| `routes/report.py` | Report endpoints (mounted at `/reports`) |
| `routes/export.py` | Session export endpoints (report / transcript download, mounted at `/records`) |
| `services/` | `report_store.py`, `report_events.py` (live report events), `debrief_runner.py`, `ingest.py`, `legacy_fallback.py`, `export.py` (report / transcript export) |
| [`agents/report/`](agents/report/README.md) | Report agent (two-stage ReAct pipeline) |
| `models/report.py` | Report tables |
| `schemas/` | `history.py` (history list responses), `report.py` (debrief report payload, including legacy per-turn review blocks) |
| `column_migrations.py` | Column-level migrations |

Tests: `apps/api/tests/records/`.
