# growth/

成长域:从面试历史派生的统计(聚合统计、洞见)。

| 层 | 内容 |
| --- | --- |
| `routes/router.py` | 成长 HTTP API(历史、洞见、聚合统计;挂载于 `/growth`) |
| `services/` | `ingest.py`、`learning.py`、`persist_from_summary.py` |
| `agents/growth.py` | 成长 agent |
| `models/growth.py` | 成长表 |
| `column_migrations.py` | 列级迁移 |

测试:`apps/api/tests/growth/`。
