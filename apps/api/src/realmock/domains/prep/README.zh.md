# prep/

Prep 面试教练域:带工具的 agent 会话、长期记忆、用量统计。

| 层 | 内容 |
| --- | --- |
| `routes/` | `chat.py`、`create.py`、`history.py`、`lists.py`、`manage.py`、`memories.py` |
| [`agents/`](agents/README.zh.md) | agent 循环与工具机制:`tools/`(注册表 + `basic/` `candidate/` `memory/` `repo/` `system/`)、`context/`(seed / working / linked / hints / markers)、`ask_user/`、流式、轮次状态、轮次压缩、quiz 渲染、持久化 |
| `services/` | `memories.py`、`linking.py`(跨会话链接)、`session_notes.py`、`session_stats.py`、`turn_lock.py`(同会话轮次串行化) |
| `models/` | 教练会话与长期记忆(表在 `sessions.db`;单用户应用,无 owner 列) |
| `main.py` / `startup.py` | 独立组装与生命周期钩子 |
| `column_migrations.py` | prep 表的列级迁移 |

测试:`apps/api/tests/prep/`。
