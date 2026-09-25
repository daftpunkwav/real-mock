# growth/

Growth domain: statistics and AI analysis derived from interview history (aggregated stats, system insights, LLM growth insight).

| Layer | Contents |
| --- | --- |
| `routes/router.py` | Growth HTTP API (history, insights, aggregated stats; mounted at `/growth`) |
| `services/` | `ingest.py` (report-summary hook), `learning.py`, `persist_from_summary.py`, `insight_scheduler.py` (single-flight background regen), `insight_store.py` (latest-insight persistence) |
| `agents/growth.py` | Rule-based agent aggregating history into page-level stats |
| `agents/insight.py` | LLM growth-insight agent: bounded tool loop over history / resume / profile evidence |
| `agents/tools.py` | Interview-history agent tools (`history_list_sessions` / `history_get_report`) |
| `prompts.py` | Insight system prompt and user-message builder |
| `models/growth.py` | Growth tables |
| `models/insight.py` | `growth_insights` table (latest insight per profile) |
| `column_migrations.py` | Column-level migrations |

Tests: `apps/api/tests/growth/`.
