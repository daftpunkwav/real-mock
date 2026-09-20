# interview/

拟真面试房域:实时 WebSocket 对话、多轮流程、裁定与报告。

| 包 | 用途 |
| --- | --- |
| [`agents/`](agents/README.zh.md) | LLM 角色,一角色一子包:`interviewer/`(主面试官)、`topology/`(影子评估、编码考官、流程编排)、`hint/`、`planning/`、`research/`、`memory/`。包 `__init__` 即门面 — `realtime` / `routes` / `process` 仅依赖门面加 `events` / `agent_text` 两个叶子契约 |
| `realtime/` | WebSocket 运行时(handler、stacks、turn / media / control、音频引擎)— 见 [realtime/README.zh.md](realtime/README.zh.md) |
| `process/` | 多轮流程编排与轮次摘要 |
| `protocols/` | plan / round-plan schema、确定性轮次链、流程记忆文档 |
| [`capabilities/`](capabilities/README.zh.md) | 面试专属能力:`rag/`、`sandbox/`(编码)、`vision/` |
| `ledger/` | append / freeze 会话台账(interview 是唯一写方) |
| `routes/` | `sessions.py`、`interview.py`、`turns.py`、`processes.py`、`options.py`、`brief.py`、`ws/`(WebSocket 端点) |
| `models/` | `session.py`、`process.py`、`brief.py`、`ws_lease.py` |
| `schemas/` | session / process / options 的 pydantic 模型 |
| `workflows.py` + `constants.py` | 阶段 / 工作流 SSOT(由 `tests/interview/test_phase_ssot.py` 与前端 `config/phases.ts` 锁定对齐) |
| `main.py` / `startup.py` / `column_migrations.py` | 生命周期钩子与列级迁移 |

测试:`apps/api/tests/interview/`(流程、realtime、agents、协议 schema)。
