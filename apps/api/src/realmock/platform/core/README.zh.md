# platform/core/

所有域共享的内核工具:与配置相邻的常量、错误注册表、日志、SSE、限流、密钥加密、安全辅助与会话认证。上层地图见 [../README.zh.md](../README.zh.md)。

## 顶层模块

| 模块 | 职责 |
| --- | --- |
| `constants.py` | 全局协议常量——与前端 `src/config/*.ts` 一一对应的字符串字面量 |
| `errors.py` | 全站错误码注册表;catalog 即权威——新错误码先在这里注册(`raise_error`) |
| `error_handlers.py` | 统一异常处理器与错误信封构造;app factory 只负责注册 |
| `logging.py` | 结构化 JSON 风格日志,含 trace id;`RedactFilter` 自动替换日志中的 API Key / Authorization 头 |
| `sse.py` | 共享 SSE 辅助:错误信封(业务错误保留 catalog 码 / 消息 / 可重试标记)、队列泵、流式响应 |
| `ratelimit.py` | 轻量进程内限流(无外部服务),保护昂贵端点(LLM 调用、上传、解析) |
| `file_lock.py` | 跨进程文件锁:Windows 用 `msvcrt.locking`,POSIX 用 `fcntl.flock` |
| `migrate.py` | SQLite 列补全迁移引擎 + `api.db` manifest + Alembic 版本戳;业务 DDL 由各域自己的 `column_migrations.py` 持有 |
| `local_only.py` | 本地暴露防护:`require_local_peer`(管理端点仅限 loopback 对端)与挂载层跨站防护(`Sec-Fetch-Site` / Origin-Referer,错误码 `A0403`) |
| `secrets.py` | 存储供应商密钥的 AES-256-GCM 认证加密(`enc:v2:...`);密钥来自 `SECRET_KEY` 环境变量或 `data/.secret.key` |
| `prompts.py` | 共享 agent/LLM 提示词片段;输出规则统一走 `with_agent_output_rules` |
| `background.py` | `spawn_background`:fire-and-forget 后台任务派生,持有在飞任务引用(防 GC 提前回收),崩溃只记日志不外抛 |
| `agent_error_log.py` | agent 工具/循环失败的可选 JSONL 日志(`REALMOCK_AGENT_ERROR_LOG=1`);默认关闭 |

## `security/` — 输入与 URL 安全

| 模块 | 职责 |
| --- | --- |
| `file.py` | 文件名清洗(取 basename、字符白名单、长度上限)、路径穿越防御、魔数嗅探 |
| `url.py` | URL/SSRF 过滤:私网 / CGNAT / 组播网段、端口白名单、多 A 记录 + IPv6 解析;策略函数留在本模块(测试 patch `url._resolve_all`) |
| `url_pin.py` | DNS pinning:解析一次、连接固定 IP(缓解 DNS rebinding TOCTOU);httpx 的 `PinnedHostTransport` |
| `redact.py` | 形似 API Key 的字符串脱敏 |

## `session_auth/` — 会话能力 token

无多用户登录;变更类操作须携带会话创建时签发的 `access_token`,默认经
HttpOnly cookie 下发(`iv_{id}` / `prep_{id}`);`X-Interview-Token` header
保留给测试与迁移;生产环境拒绝 query string 传 token。

| 模块 | 职责 |
| --- | --- |
| `cookies.py` | Cookie 命名 / 写入 / 清除、Secure 判定,能力 cookie 90 天有效期 |
| `tokens.py` | token 生成(url-safe,约 32 字节熵)与常数时间比较 |
| `csrf.py` | cookie-only 路径的 CSRF 缓解:Origin/Referer 须在 CORS 白名单内 |
| `extract.py` | 按作用域从 cookie / header / (仅 dev) query 提取 token |

测试:`apps/api/tests/platform_core/`,会话级集成在 `apps/api/tests/sessions/`。
