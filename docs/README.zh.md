# 文档

覆盖整个仓库的主题指南。目录级结构见代码旁的 README(从 [README.md](../README.md) 开始);工作流与贡献规则见 [CONTRIBUTING.zh.md](../CONTRIBUTING.zh.md)。

## 系统

| 文档 | 内容 |
| --- | --- |
| [架构](architecture.zh.md) | 模块化单体:platform / domains / bootstrap、依赖规则与守卫测试、进程组装 |
| [面试流程](interview-flow.zh.md) | 阶段工作流、多轮流程、轮次规划、过程记忆、裁定与报告链 |

## 子系统(`subsystems/`)

| 文档 | 内容 |
| --- | --- |
| [Agent 体系](subsystems/agent-system.zh.md) | think-then-act 循环、工具与执行隔离、上下文管理、LLM 协议栈、模型能力声明 |
| [语音](subsystems/voice.zh.md) | STT 路由与回退、TTS 供应商、语音目录、面试房音频链路 |
| [前端](subsystems/frontend.zh.md) | 页面、feature 模块、i18n、契约类型、浏览器代码执行、房间 hook、媒体采集 |

## 接口(`interfaces/`)

| 文档 | 内容 |
| --- | --- |
| [HTTP API](interfaces/api.zh.md) | 路由挂载、访问控制、按域端点、OpenAPI 契约流水线 |
| [实时协议](interfaces/realtime-protocol.zh.md) | 面试 WebSocket:端点、握手、帧格式、完整事件词汇表 |
| [数据模型](interfaces/data-model.zh.md) | 双 SQLite 库、表、迁移机制、运行时数据位置、SQLite PRAGMA |

## 工程与运维(`operations/`)

| 文档 | 内容 |
| --- | --- |
| [配置](operations/configuration.zh.md) | Settings 字段与环境变量、启动校验、BYOK 存储、密钥加密 |
| [安全](operations/security.zh.md) | 环回守卫、会话认证、SSRF pin、静态密钥加密、密钥脱敏、文件处理 |
| [测试](operations/testing.zh.md) | 后端与前端套件、架构与契约守卫测试、CI 门禁 |
| [部署](operations/deployment.zh.md) | CI 工作流、容器镜像、运行时数据卷 |

每份指南的中文版即为同目录下的 `<name>.zh.md`(英文版为 `<name>.md`)。
