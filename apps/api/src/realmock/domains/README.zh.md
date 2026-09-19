# domains/

业务域。七个独立模块,由 `platform/router_mount.py` 挂载。

| 域 | 用途 |
| --- | --- |
| [`profile/`](profile/README.zh.md) | 候选人档案(单租户;PUT 全量替换语义) |
| [`resume/`](resume/README.zh.md) | 简历上传、解析、深度评价、分页预览 |
| [`settings/`](settings/README.zh.md) | 供应商 / 模型 / 阶段设置与集成(GitHub 关联、模型测试) |
| [`prep/`](prep/README.zh.md) | Prep 面试教练:带工具的 agent 会话、记忆压缩、用量统计 |
| [`interview/`](interview/README.zh.md) | 拟真面试房:实时 WebSocket、多轮流程、裁定 |
| [`records/`](records/README.zh.md) | 面试历史与报告 |
| [`growth/`](growth/README.zh.md) | 成长统计 |

## 共享分层

各域共享同一分层;域只保留自己需要的层:

| 层 | 用途 |
| --- | --- |
| `router.py` | 组装并导出域 APIRouter |
| `routes/` | HTTP / WS 端点(薄:解析、委托、序列化) |
| `services/` | 业务逻辑 |
| `agents/` | LLM agent(agent 驱动的域) |
| `schemas/` | 请求 / 响应 pydantic 模型 |
| `models/` | 域 ORM 模型(拥有表的域) |
| `main.py` / `startup.py` | 域生命周期钩子(按需) |
| `column_migrations.py` | 域表的轻量列级迁移 |

薄域(`profile/`、`settings/`)跳过不需要的层。`interview/` 最大,额外携带 `realtime/`(WebSocket 运行时,见 [interview/realtime/README.zh.md](interview/realtime/README.zh.md))、`process/`(多轮流程编排与轮次摘要)、`protocols/`(plan / round-plan schema、轮次链、流程记忆)、`capabilities/`(RAG、编码沙箱、视觉)、`ledger/`(append / freeze 会话台账)以及域根的 `workflows.py`(阶段 / 工作流 SSOT,由测试与前端 `config/phases.ts` 锁定对齐)。
