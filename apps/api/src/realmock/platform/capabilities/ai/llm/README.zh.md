# capabilities/ai/llm/

面向供应商的 LLM 调用层:一套协议栈支持三种线上协议(OpenAI chat completions、
Anthropic messages、OpenAI responses),外加所有域共享的流式后处理与输出解析。
上层地图见 [../README.zh.md](../README.zh.md)。

## `client/` — 协议栈

| 模块 | 职责 |
| --- | --- |
| `unified_client.py` | `UnifiedLLMClient` 入口,覆盖三种协议;请求体构造 / 解析 / 流式 / 端点均委托给下述模块 |
| `protocol_translate.py` | 按协议构造请求体;协议特定的消息/工具转换委托给 `anthropic_converters.py` / `responses_converters.py`(共享纯函数在 `protocol_utils.py`) |
| `response_extract.py` | 响应解析(正文 / 工具调用 / reasoning / 结束原因 / 业务错误 / 引用 / 服务端工具条目)与单事件 SSE 解析;纯函数,不发网络请求 |
| `streaming.py` | 两个客户端共享的流式传输:SSE 解析、usage 收集、`stream_options` 降级信号;首个增量前按共享重试梯度重试,供应商终态错误抛 `LLMUpstreamError` |
| `assemblers.py` | 流式工具轮增量装配器(openai_chat / anthropic / openai_responses):reasoning 增量即时返回,正文增量排队供投机流式使用,工具调用缓冲到流结束;捕获终态(结束原因、供应商错误事件、带签名的 thinking 块、refusal/搜索条目透出) |
| `chat_endpoints.py` | 非流式端点(`chat` / `test_connection` / `chat_message`),走共享的 pinned-client 路径;HTTP 成功但业务层失败(如 MiniMax base_resp)抛 `LLMUpstreamError` |
| `retry_stream.py` | 流式重试:429/5xx/连接错误在首个增量前按共享梯度重试;4xx 不重试;`stream_options` 被拒时降级重放 |
| `json_response.py` | `chat_json` 的 JSON 输出解析:剥离 think/代码围栏、有界宽容重试;失败保持可见,绝不伪造 JSON |
| `llm_client.py` | `LLMClient`,OpenAI 兼容的 BYOK 客户端;每次请求对 `api_base` 做 SSRF 校验,自动解密库内密钥 |
| `openai_transport.py` | `LLMClient` 的 chat 协议执行、JSON 输出解析修复、embeddings 调用 |
| `llm_client_ext.py` | `LLMClient` 出站探测(`test_connection`)与 `embed` |
| `from_db.py` | 按模型档案装配客户端(能力声明制 task 绑定);自定义思考档位(`extras.reasoning.variants`)逐字透传;场景显式指定 profile 时不静默回退 |

## 协议栈外围

| 模块 | 职责 |
| --- | --- |
| `stream_filters.py` | 流式清洗公开入口 |
| `stream_sanitizer.py` | 双通道(reasoning/正文)清洗编排 |
| `special_token_filter.py` | 流式安全剥离训练模板 token(`<|X|>` / `<]X[>` 两种形态) |
| `inline_tool_call.py` | 移除泄漏进正文的 XML `<tool_call>` 块(协议漂移);保留有效的 `<question>` 内容 |
| `say_first_stream.py` | say-first 结构化流式:`{"say": ...}` 首键增量送往语音/字幕通道,其余键在流结束时整体解析为控制字段 |
| `json_extract.py` | 从含噪输出中恢复 JSON 对象:字符串感知的配平括号扫描,保留键最多的候选 |
| `usage.py` | 三协议通用的 token usage 提取与累加,外加单请求诊断(上游 request id、耗时、最近错误) |
| `retry_policy.py` | 出站 LLM 调用的共享重试梯度:最多重试 10 次(10/10/20/20/40/40/80/80/100/100 秒),供应商 `Retry-After` 头对当次重试优先;ReadTimeout 永不重试 |
| `defaults.py` | token 预算默认值;用户配置的 context window / max output 优先于这些常量 |
| `provider_errors.py` | 保守的供应商侧上下文溢出分类,供调用方压缩后重试 |
| `unified_client.py`、`tool_args.py` | 兼容包装,从 `client/` 再导出 |

测试:`apps/api/tests/platform_ai/`。
