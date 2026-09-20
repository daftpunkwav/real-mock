# 安全

逐机制描述代码中实际存在的安全机制。以下路径均位于 `apps/api/src/realmock/platform/core/`,已逐一核验。这些机制的适用边界即项目自我声明的部署边界:本地优先、单用户、不上公网 — 代码中不存在多用户登录与多实例机制(`session_auth/__init__.py`),因此下述每个机制都在这一单进程、面向环回的边界内生效。

## 仅环回访问(`local_only.py`)

| 守卫 | 行为 |
| --- | --- |
| `require_local_peer(request)` | 本地管理端点仅接受环回对端;非环回 IP 以 `A0405` 拒绝。Starlette `testclient` 对端始终放行;`TEST_MODE=1` 仅在非生产环境放行真实 HTTP(`env=prod` 时忽略)。FastAPI 无法在 WebSocket 作用域注入 `Request`,因此 WS 端点以 `request=None` 调用,此时守卫短路 — WS 端点改经会话能力令牌认证。 |
| `reject_cross_site_fetch(request)` | 拒绝浏览器驱动的跨站请求(`Sec-Fetch-Site: cross-site`),返回 `A0403`。非浏览器客户端(curl)不发送该头,直接放行。仅限 HTTP;WS 作用域 `request=None` 时短路。 |
| `guard_ws_origin(websocket)` | 跨站 WS 握手在 accept 之前关闭(关闭码 1008)。浏览器必发 `Origin`;主机名必须是 `localhost` / 环回 IP;无 Origin(非浏览器)放行。 |

`LOCAL_API_DEPENDENCIES` 组合两个 HTTP 守卫,是路由挂载层统一的访问控制唯一定义;各路由不再自行声明。

## 会话认证(`session_auth/`)

按会话的能力令牌 — 本地优先产品不引入多用户登录;变更型操作(WS / start / message / finish / messages / reports / prep)需要会话创建时签发的 `access_token`。

| 模块 | 机制 |
| --- | --- |
| `tokens.py` | `new_access_token()` — url-safe 令牌,约 32 字节熵(`secrets.token_urlsafe(32)`);`tokens_match()` 常数时间比较;`assert_session_token()` 断言助手。 |
| `cookies.py` | HttpOnly cookie,名为 `iv_{id}` / `prep_{id}`(作用域 `CookieScope = Literal["iv", "prep"]`),有效期 `COOKIE_MAX_AGE` = 90 天;`cookie_should_be_secure()` 决定 Secure 标志。 |
| `extract.py` | HTTP 提取顺序:`X-Interview-Token` 头 > cookie > query;WebSocket 经 `mock.<token>` 子协议前缀提取。生产环境拒绝 query `?token=`(防代理 / 访问日志泄露)。仅 cookie 认证路径上,提取时会调用 CSRF 校验。 |
| `csrf.py` | `assert_csrf_if_cookie_only()` — Origin / Referer 必须命中 CORS 允许列表(`cors_origin_list`),作为 cookie 认证的 CSRF 缓解。 |

## 出站请求防护(`security/url.py`、`security/url_pin.py`)

带 DNS pinning 的 SSRF 过滤,供 agent `fetch` 工具与 LLM 客户端使用:

- `_resolve_all()` 将主机名解析为全部候选 IP(IPv4 + IPv6)。任一解析地址不安全即拒绝该 URL。
- 默认阻断网络:环回、链路本地(`169.254.0.0/16`,元数据端点)、私有网段、CGNAT、组播、保留段及 IPv6 等价段。`allow_local=True` 额外放行的仅有环回 — 私有网段与元数据仍然阻断。
- 端口允许列表:默认仅 80 / 443(`_DEFAULT_ALLOWED_PORTS`);显式 `allowed_ports` 集合无论 `allow_local` 与否都强制执行。
- DNS 重绑定缓解:`pin_safe_http_url()` 只解析一次,校验全部候选,并将首个安全 IP 固定进 `PinnedHttpTarget`;`PinnedHostTransport` 将请求主机改写为固定 IP,同时保留 `Host` 头与 SNI 主机名;`make_pinned_async_client()` 构造 `follow_redirects=False` 的 `httpx.AsyncClient`。
- 代理 fake-IP 例外段:`198.18.0.0/15` 始终放行,并以 `FAKEIP_ALLOWED_HOSTS` 限定域名(`url.py` 中列出的 `xiaomimimo.com` API 主机)。
- agent fetch 工具逐跳跟随重定向:每一跳都新建固定 IP 的客户端(最多 5 跳,`_MAX_REDIRECT_HOPS`),重定向目标因此经过同一套策略校验。LLM 客户端以 `is_safe_http_url()` 校验 `api_base`,并经固定 IP 客户端发请求(`client/retry_stream.py`)。

## 密钥静态加密(`secrets.py`)

- AES-256-GCM 认证加密(`cryptography.hazmat.primitives.ciphers.aead.AESGCM`);每段密文使用随机 16 字节盐与 12 字节 nonce;32 字节 AES 密钥由主密钥经 PBKDF2-HMAC-SHA256(200,000 次迭代)按密文派生。
- 密文格式 `enc:v2:<b64-salt16>:<b64-nonce12>:<b64-tag16>:<b64-cipher>`。
- 主密钥来源:`SECRET_KEY` 环境变量(base64 或明文,≥16 字节由 `validate_master_key_env()` 校验;`asgi.py` 启动门禁 `_check_secret_key_policy` 在 `env=prod` 时强制),或自动生成的密钥文件 `data/.secret.key`(权限 0600)。
- 旧 `enc:v1` 密文抛出 `LegacySecretFormatError` — 不做静默迁移;用户在设置页重新保存密钥。未加密的明文值原样通过。
- 用途:供应方通道 API key 写入时加密(`domains/settings/services/model_registry.py` 的 `apply_channel_key`),`UnifiedLLMClient` 读取时解密(`decrypt_secret`)。

## API key 日志脱敏(`security/redact.py`)

`redact_api_key()` 为日志输出脱敏 API key:PEM 块替换为 `***PEM_REDACTED***`;`Authorization` / `Bearer` / `Token` / `Basic` 头仅保留方案名;可识别的 key 形态(`sk-`、`sk-ant-`、Google `aiza` 前缀)与启发式判定为密钥的字符串(≥20 字符、字母数字混合、无空格)渲染为 `首4***末4`。调用方包括 LLM 客户端、STT 供应方、平台日志配置(`core/logging.py`)以及域内路由 / 工具守卫的错误路径。

## 文件处理(`security/file.py`)

`sanitize_filename()`(ASCII 安全文件名,上限 120 字符)、`assert_within_dir()`(路径穿越遏制)、`sniff_extension()`(`pdf` / `docx` / `doc` 容器的扩展名 ↔ 魔数校验)。
