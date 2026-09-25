# growth/

成长域:从面试历史派生的统计与 AI 分析(聚合统计、系统洞察、LLM 成长洞见)。

| 层 | 内容 |
| --- | --- |
| `routes/router.py` | 成长 HTTP API(历史、洞见、聚合统计;挂载于 `/growth`) |
| `services/` | `ingest.py`(报告摘要钩子)、`learning.py`、`persist_from_summary.py`、`insight_scheduler.py`(单飞后台重生成)、`insight_store.py`(最新洞见持久化) |
| `agents/growth.py` | 基于规则的 agent,把历史聚合为页面级统计 |
| `agents/insight.py` | LLM 成长洞见 agent:在历史 / 简历 / 档案证据上跑有界工具循环 |
| `agents/tools.py` | 面试历史 agent 工具(`history_list_sessions` / `history_get_report`) |
| `prompts.py` | 洞见系统提示词与用户消息构建 |
| `models/growth.py` | 成长表 |
| `models/insight.py` | `growth_insights` 表(每档案一行最新洞见) |
| `column_migrations.py` | 列级迁移 |

测试:`apps/api/tests/growth/`。
