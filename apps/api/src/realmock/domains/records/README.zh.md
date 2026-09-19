# records/

记录域:面试历史与报告。

| 层 | 内容 |
| --- | --- |
| `routes/history.py` | 历史端点(挂载于 `/records`) |
| `routes/report.py` | 报告端点(挂载于 `/reports`) |
| `services/` | `report_store.py`、`report_events.py`(报告实时事件)、`debrief_runner.py`、`ingest.py`、`legacy_fallback.py` |
| `agents/report/` | 报告 agent |
| `models/report.py` | 报告表 |
| `column_migrations.py` | 列级迁移 |

测试:`apps/api/tests/records/`。
