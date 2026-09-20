# platform/

平台内核:所有域共享的基础设施。域依赖本包;反向依赖是架构违规(由 `tests/architecture/test_platform_no_domain_imports.py` 守护)。

## 包

| 包 | 用途 |
| --- | --- |
| `capabilities/` | 外部能力适配器:[`ai/`](capabilities/ai/README.zh.md)(LLM 供应商、agent loop、上下文管理)、`integrations/github/`、`knowledge/search/`、[`voice/`](capabilities/voice/README.zh.md)(STT / TTS / 语音配置) |
| `contracts/` | 跨域事件与数据契约(interview finished、session score、report summary、session catalog、lifecycle hooks) |
| [`core/`](core/README.zh.md) | 内核工具:常量、错误与处理器、日志、文件锁、local-only 守卫、DB 迁移助手、agent 错误日志、共享提示词片段、进程内限流、secrets 加密、SSE 助手、安全助手(文件 / URL pin / 脱敏)、会话认证(cookies、CSRF、tokens) |
| `catalogs/` | 静态参考目录(公司) |
| `models/` | 共享模型(配置模型、限流桶) |
| `schemas/` | 共享 pydantic schema(candidate、pipeline、errors) |
| `services/` | 共享服务(candidate read 门面、DB 拆分、resume picker、seed、pipeline) |
| `vendors/` | 厂商适配器描述符(JSON defs)与模板助手(深合并、占位符替换) |
| `data/` | 运行时数据(SQLite 数据库、Chroma store)。`stt_fixtures/` 是纳入跟踪的测试数据;其余为运行时所有、不入库 |
| `uploads/` | 运行时用户上传文件(不入库) |

## 顶层模块

| 模块 | 用途 |
| --- | --- |
| `app_factory.py` | FastAPI 应用构建 |
| `router_mount.py` | 域路由挂载 |
| `config.py` | 配置 |
| `database.py` | 数据库装配 |
