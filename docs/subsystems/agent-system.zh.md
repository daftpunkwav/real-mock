# Agent 系统

平台级 agent 机制位于 `apps/api/src/realmock/platform/capabilities/ai/`:通用 think-then-act 循环(`agent/`)、上下文窗口管理(`context/`)与 LLM 供应方调用层(`llm/`)。域包在其上实例化:[prep agents](../../apps/api/src/realmock/domains/prep/agents/README.md) 与 [interview agents](../../apps/api/src/realmock/domains/interview/agents/README.md)。

## `agent/` — think-then-act 循环

| 模块 | 用途 |
| --- | --- |
| `loop.py` | `run_agent_loop()` 驱动工具轮次,直到模型不再请求工具或达到 `max_rounds`;结果为 `LoopResult`(`messages`、`final_content`、`tool_used`、`halted`、`thinking`)。不带 `tool_calls` 的正文即最终答案并结束循环。同一轮的多个工具调用并行执行(`asyncio.gather`);超出 `max_tools_per_round`(默认 8)的调用仍保留在 assistant 消息中声明,并收到明确的"未执行"观察。最后一轮注入收尾提示;循环因 `AgentHalt` 而终止;`ApiBusinessError` 向调用方传播。 |
| `llm_round.py` | `_call_llm_round()` — 每轮一次模型调用,优先流式 `chat_message_stream`(推理增量实时可见),客户端缺少流式或协议不支持时回退非流式 `chat_message`。另含 `_truncate_tool_result`,上限为 `TOOL_OBSERVATION_SOFT_CHARS`(12,000)。 |
| `events.py` | 进度事件契约:`AgentEvent`(dict)、`OnAgentEvent` 接受同步或异步回调,`emit_agent_event()` 统一发射并 await 回调;回调失败仅记日志,绝不抛出。 |
| `halt.py` | `AgentHalt` — 工具请求立即结束循环的信号(其 message 作为工具观察写回)。 |
| `hints.py` | 收尾提示(`_WRAP_UP_HINT`)与跑偏纠正提示(`_DRIFT_HINT`):使用工具前出现简短无动作叙述时触发一次纠正重试。 |
| `working_memory.py` | `WorkingMemory` — 压缩后仍留在模型可见上下文中的结构化事实,以 `MEMORY_MARKER`(`[Working memory]`)标记。 |

## `agent/tools/` — 共享工具集

| 模块 | 用途 |
| --- | --- |
| `spec.py` | `ToolSpec`(OpenAI 函数 schema + 异步 handler)与 `ToolBundle`(agent 循环使用的有序注册表/分发器)。 |
| `executor.py` | `invoke_with_timeout()` — 单次调用的超时 + 错误分类;超时与意外异常以 JSON 观察返回(`"timeout"` / `"tool_failed"`),`ApiBusinessError` 向上抛出。 |
| `github.py` | 包装 `capabilities/integrations/github/tools`(`GITHUB_TOOL_DEFINITIONS`、`execute_github_tool`),各域共享同一 schema + 执行路径。 |
| `search.py` | 公网搜索工具;结果数受 `SEARCH_DEFAULT_MAX_RESULTS`(8)/ `SEARCH_HARD_MAX_RESULTS`(12)约束。 |
| `fetch.py` | 公网网页抓取,带 SSRF 防护(见 [security.zh.md](../operations/security.zh.md));重定向逐跳跟随(最多 5 跳),输出硬上限(6,000 / 12,000 字符)。 |
| `profile.py` | 分层用户画像工具:`profile_list_sections` / `profile_get_section`,五个分区(`basics`、`education`、`career`、`skills`、`links`)。 |
| `resume.py` | 渐进披露的简历工具:`resume_overview` / `resume_get_section`(分区含分页原文摘录)。 |
| `codeexec.py` | 沙箱化 Python / JavaScript 代码片段执行器;隔离后端由 `run_code_snippet(..., isolation=...)` 按次选择,默认 `"auto"`。 |

### `tools/isolation/` — 执行隔离后端

两个后端均实现 `base.py` 中的 `IsolationBackend` 协议(`spawn` / `describe`),返回 `CompletedSnippet`(`exit_code`、`stdout`、`stderr`、`timed_out`、`notes`)。后端绝不因代码片段行为而抛异常;退出码与超时都是数据。`base.run_child()` 超时时杀死整个进程树(`terminate_tree`,POSIX 下经 `killpg` 杀进程组)。

| 后端 | 强制控制 |
| --- | --- |
| `process.py`(`ProcessIsolation`) | 墙钟超时、私有临时工作目录、净化环境。不切换用户、不阻断网络、无 cgroup 限额。Windows、开发机与非 root 进程下的默认后端。 |
| `linux_job.py`(`LinuxJobIsolation`) | 仅限 Linux。切换到非特权账户(默认 `nobody`,经 `setpriv` / `runuser`),全新网络命名空间(`unshare -n`,loopback 亦关闭),`/sys/fs/cgroup/realmock-codeexec` 下的 cgroup v2 `memory.max`(默认 256 MiB)与 `cpu.max`(默认 `50000 100000` — 半个 CPU),并在私有挂载命名空间内尽力将 `/` 重挂载为只读。通过探测 OS 助手选择启动策略,优先级:`contained` > `userns-mapped` > `userns-netonly` > `netonly` > `plain`。无法强制执行的控制一律以 `<control>=unavailable` 显式记入 `notes` — 绝不静默降级。可用 `CODEEXEC_*` 环境变量调节。 |

## `context/` — 上下文窗口管理

| 模块 | 用途 |
| --- | --- |
| `manager.py` | 入口;`prepare_llm_context` 编排(压缩 + 以独立 system 分区注入工作记忆)。 |
| `estimation.py` | 面向预算检查的按文字系统粗估 token(中文 ≈ 1.5 字符/token,拉丁文 ≈ 4);图片 data URL 按 32 字符/token 计,并预留窗口的 `VISION_CONTEXT_IMAGE_RATIO`(0.35)。 |
| `compress.py` | 规则式 `compress_messages`(保留 system 消息 + 最近尾部 + 摘要行)与折叠陈旧工具调用对;产物标记 `[Conversation Minutes]` / `[Context compression]`。 |
| `summarize.py` | `compact_with_summary` — 超阈值时由 LLM 生成分段纪要,增量替换被省略的对话;LLM 失败回退规则式摘要(记日志、可见),`force=True` 时不回退。 |
| `blobs.py` | 超长文本 blob 的 LLM 压缩;失败时返回显式标记的首尾摘录。 |
| `options.py` | `CompactionOptions` 值对象;强度档位 `light` / `balanced` / `aggressive`,逐字保底尾窗分别为 10 / 4 / 0 条消息。 |

## `llm/` — 面向供应方的模型调用

包根的 `unified_client.py` 是向后兼容包装;实现在 `client/` 协议栈中:

| 模块 | 用途 |
| --- | --- |
| `client/unified_client.py` | `UnifiedLLMClient` — 按协议字段选择 API 路径:OpenAI chat completions / Anthropic messages / OpenAI Responses。持有客户端状态、SSRF 检查、URL 与载荷构造、流式编排;供应方配置经 `from_db.py` 从数据库加载。 |
| `client/llm_client.py` | 客户端方法,含 `chat_message_stream`(流式工具轮)。 |
| `client/retry_stream.py` | OpenAI 兼容流式执行:首个增量发出前,429 / 5xx / 连接错误按指数退避重试(默认 3 次);4xx 不重试(被拒绝的 `stream_options` 字段移除后重放);增量已发出后的失败直接抛出。 |
| `protocol_translate.py` / `response_extract.py` / `assemblers.py` / `chat_endpoints.py` / `streaming.py` | 请求体构造、响应解析、增量流装配器、非流式端点、流式执行。 |

流后处理(入口 `stream_filters.py`):`special_token_filter.py` 跨 chunk 边界流式剥离训练模板 token(`<|X|>` / `<]X[>`);`inline_tool_call.py` 清理函数调用退化为正文中的 `<tool_call>` XML;`StreamSanitizer` 双通道编排两者,并将推理增量包裹为 `<think>...</think>`。`say_first_stream.py` 从流中增量解析 `{"say": "...", ...}` 输出 — 第一句口语只要其句末标点到达即被发出;降级链(缺 `say` 键、JSON 解析失败)回退为纯文本。

## 模型能力声明

`domains/settings/services/model_registry.py` 是基于能力的声明系统,覆盖四张数据库表(`platform/models/config_models.py`):

| 表 | 内容 |
| --- | --- |
| `LlmProvider` | 供应方条目(名称、启用、网址、备注)。 |
| `LlmProviderChannel` | 按种类的连接配置;种类为 `chat` / `stt` / `tts`(`CHANNEL_KINDS`)。 |
| `ModelProfile` | 单个模型条目:上下文窗口、最大输出、能力位 `cap_chat` / `cap_vision` / `cap_audio_in` / `cap_audio_out` / `cap_reasoning`,以及 `extras` 约定键 `reasoning`(variants、defaultVariant)与 `modalities`(input / output)。 |
| `TaskBinding` | 将每个任务(`chat` / `stt` / `tts`)绑定到一个模型条目并附回退处理器;条目能力位不覆盖任务时绑定被拒绝。 |

HTTP 面:`domains/settings/routes/models.py` 与 `domains/settings/routes/model_tests.py`。

## 域级实例

- **Prep agents** — [`domains/prep/agents/`](../../apps/api/src/realmock/domains/prep/agents/README.md):轮次编排(`chat.py`、`agent.py`)、每轮工具集策略(`turn_tools.py`)、带 `ask_user` 分发的工具执行回调(`tool_exec.py`;`ask_user` 工具发出 `ask_user` 事件并抛出 `AgentHalt`)、轮内压缩(`round_compaction.py`,`MidTurnCompaction`)、投机流式(`streaming.py`)、持久化(`persist.py`);子包 `context/`、`ask_user/`、`tools/`(家族 `basic/`、`candidate/`、`memory/`、`repo/`、`system/`)。
- **Interview agents** — [`domains/interview/agents/`](../../apps/api/src/realmock/domains/interview/agents/README.md):每角色一个子包(`interviewer/`、`topology/`、`hint/`、`planning/`、`research/`、`memory/`),共享内核平铺在包根。包 `__init__` 即 facade:`realtime` / `routes` / `process` 只依赖它以及两个叶契约 `agents.events` 与 `agents.agent_text`。`say_first.py` 为面试轮次解析 say-first 协议。
