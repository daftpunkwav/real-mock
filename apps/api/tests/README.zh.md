# tests/

后端测试套件。布局与源码树镜像:每个域一个目录,外加平台与跨切面套件。运行方式 `cd apps/api && pytest`(`testpaths = tests`)。

## 域套件

| 目录 | 覆盖 |
| --- | --- |
| `profile/` | profile 域 |
| `resume/` | resume 域(解析、评价流水线、契约) |
| `settings/` | settings 域 |
| `prep/` | prep 域(agent 流、工具、记忆、压缩) |
| `interview/` | interview 域(流程、追问、裁定) |
| `records/` | records 域(报告 agent) |
| `growth/` | growth 域 |

## 平台与跨切面套件

| 目录 | 覆盖 |
| --- | --- |
| `platform_core/` | 平台内核(core 工具、配置、数据库) |
| `platform_ai/` | AI 能力(LLM、agent 上下文、压缩) |
| `sessions/` | 会话级集成:auth、限流、SSRF pin、WS 互斥、流式 |
| `voice/` | 语音能力(voice config、resolve、TTS) |
| `architecture/` | 架构守卫测试:platform 不得 import domains、domains 不得互相 import、DB 边界、API 路径约定 |
| `smoke/` | 跨平台与域服务的聚合启动冒烟 |

## 共享 fixture

| 文件 | 用途 |
| --- | --- |
| `conftest.py` | 共享 pytest fixture |
| `fakes.py` | 共享测试替身 |
