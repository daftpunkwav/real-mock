# 安全策略

## 支持版本

安全修复落在 `main` 分支,并随最新 tag 版本发布(当前为 `v0.1.0`)。更早的
tag 不做回移。

## 部署形态

RealMock 是本地优先的单用户应用。`scripts/dev.sh` 将后端绑定到
`127.0.0.1:8081`;前端 dev server 监听 `8080` 端口,Next.js 默认绑定全部
网卡接口,请勿暴露在不受信网络中。模型供应商密钥由
用户自带(BYOK),落盘加密存储。将后端暴露到 loopback 之外(例如
`--host 0.0.0.0`)不是受支持的部署方式;下述防护能缓解但不会为这种部署做设计。

## 漏洞报告

请通过邮件私下报告:**daftpunk.wav@outlook.com**。安全报告请勿提公开 issue。

请附上问题描述、复现步骤或 PoC、受影响路径,以及你对严重程度的评估。会在
7 天内确认收到,修复推进期间同步状态。

## 安全相关面

按大致优先级排列(路径相对仓库根目录):

- **本地暴露防护** — `apps/api/src/realmock/platform/core/local_only.py`:
  `LOCAL_API_DEPENDENCIES`(经 `require_local_peer` 的 loopback 校验、浏览器
  跨站拒绝、非安全方法的同源校验)挂载在全部七个业务路由
  (profile / resume / settings / interview / prep / records / growth)上;
  `ENV=prod` 下对非 loopback 对端忽略 `TEST_MODE`
  逃生开关。同一模块还提供挂载层跨站防护(`Sec-Fetch-Site` 与
  Origin/Referer 校验,错误码 `A0403`),覆盖全部业务路由,含 WS 握手。
- **SSRF 防护** — `apps/api/src/realmock/platform/core/security/url.py` 与
  `url_pin.py`:任何出站请求前做 URL 校验(私网 / CGNAT / 组播网段、端口
  白名单、多 A 记录 + IPv6 解析),并通过 DNS pinning(解析一次、连接固定
  IP)缓解 DNS rebinding 的 TOCTOU。
- **代码片段沙箱** —
  `apps/api/src/realmock/platform/capabilities/ai/agent/tools/isolation/`:
  agent 代码执行隔离。`process.py` 强制墙钟超时、独立工作目录与清洗后的
  环境变量(Windows 默认);`linux_job.py` 追加非特权用户、无接口的网络
  namespace、cgroup v2 内存/CPU 上限。无法强制的控制项会以显式条目写入
  `CompletedSnippet.notes`,绝不静默降级。
- **会话认证** —
  `apps/api/src/realmock/platform/core/session_auth/`:按作用域(`iv`、
  `prep`)签发 HttpOnly 能力 Cookie,常数时间 token 比较,cookie-only 路径的
  CSRF 缓解(Origin/Referer 须在 CORS 白名单内),`ENV=prod` 拒绝 query string
  传 token(cookie 与 header 仍受支持)。
- **静态密钥加密** — `apps/api/src/realmock/platform/core/secrets.py`:存储的
  供应商密钥使用 AES-256-GCM 认证加密(`enc:v2:...` 格式;密钥来自
  `SECRET_KEY` 环境变量或 `apps/api/src/realmock/platform/data/.secret.key`)。`security/redact.py` 对日志中
  形似 API Key 的字符串做脱敏。
- **上传安全** — `apps/api/src/realmock/platform/core/security/file.py`:
  文件名清洗(取 basename、字符白名单、长度上限)与接受容器的魔数嗅探。
- **前端 URL 处理** —
  `apps/web/src/components/markdownComponents.tsx`:对模型生成的 markdown
  链接 `href` 做过滤(由
  `apps/web/src/components/__tests__/markdownSafeUrl.test.ts` 守护)。

上述清单之外的问题同样欢迎。`apps/api/tests/architecture/` 中的架构守卫测试
(分层、暴露回归)记录了这些安全面需要维持的不变量。
