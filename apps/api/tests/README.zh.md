# tests/

后端测试套件。布局与源码树镜像:每个域一个目录,外加平台与跨切面套件,以及根级的源码布局守卫。运行方式 `cd apps/api && pytest`(`testpaths = tests`)。

## 域套件

| 目录 | 覆盖 |
| --- | --- |
| `profile/` | profile 域(HTTP 契约、schema、契约守卫) |
| `resume/` | resume 域(解析、评价流水线、上传与文件端点、契约) |
| `settings/` | settings 域(模型注册表、stage 配置、vendor、数据清理) |
| `prep/` | prep 域(agent 流、工具、记忆、压缩、会话路由) |
| `interview/` | interview 域(流程、规划、realtime WS、runner、ledger、提示词、工具) |
| `records/` | records 域(报告 agent、综合、轮次笔记、导出与历史路由) |
| `growth/` | growth 域(洞察 agent、学习旁路文件、历史索引) |

## 平台与跨切面套件

| 目录 | 覆盖 |
| --- | --- |
| `platform_core/` | 平台内核(core 工具、配置、数据库、密钥与脱敏、会话鉴权、错误目录) |
| `platform_ai/` | AI 能力(LLM 传输、agent 循环与工具、上下文压缩、隔离执行) |
| `sessions/` | 会话级集成:auth、限流、SSRF pin、WS 互斥、HTTP/WS 面试流程、流式 |
| `voice/` | 语音能力(voice config、resolve、TTS、STT provider) |
| `architecture/` | 架构守卫测试:import 边界(platform 与 domains、DB 边界、interview 分层)、装配(bootstrap ORM 注册、app factory)、已发布的 REST 契约(路径约定、响应结构与媒体类型、OpenAPI 同步)、跨层契约(ledger 文档、profile 读模型、WS 错误码)、暴露面守卫(仅本地、SSRF、跨站) |
| `smoke/` | 跨平台与域服务的聚合启动冒烟 |

## 根级守卫

| 文件 | 用途 |
| --- | --- |
| `test_prompt_hygiene.py` | 源码布局守卫:提示词文案只放在所属的 prompts 模块中,不得内联在业务文件里 |

## 共享 fixture

| 文件 | 用途 |
| --- | --- |
| `conftest.py` | 共享 pytest fixture |
| `fakes.py` | 共享测试替身 |
