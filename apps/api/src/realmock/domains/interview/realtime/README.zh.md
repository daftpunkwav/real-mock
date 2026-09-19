# Interview WebSocket 实时层

## 组装

`InterviewWSHandler`(`ws_handler.py`)是**薄的组装外壳**:组合 `stacks/` 的三个栈 mixin,加上 dispatcher 与报告调度器。

| 组成 | 模块 | 职责 |
| --- | --- | --- |
| ConnectionStack | `stacks/connection_stack` ← `connection/`(lifecycle、auth、heartbeat) | 连接生命周期、认证、心跳、单标签页租约 |
| TurnStack | `stacks/turn_stack` ← `turn/`(coordinator、streaming、control) | 轮次锁与协调、流式、轮次控制 |
| MediaStack | `stacks/media_stack` ← `voice/`(pipeline、tts_queue)+ `control/hint` | STT/TTS 管线、句子级 TTS 队列、参考提纲 |
| MessageDispatcher | `core/message_dispatcher` | 客户端事件分发 |
| ReportScheduler | `report_scheduler` | 后台报告生成 |

支撑子包:

| 包 | 用途 |
| --- | --- |
| `core/` | `context`(`ConnectionContext`,状态 SSOT)、`events`、`message_dispatcher`、`session_registry`(单标签页租约 / 接管) |
| `control/` | 轮次控制 mixin(finish、interrupt、silence nudge / probe、turn timers、user text),由 `turn/control.py` 聚合 |
| `engine/` | 实时音频引擎抽象:cascaded(STT → LLM → 句子 TTS)与 native 全双工,附 factory |
| `nudge/` | 无状态沉默追问模板,按 phase / persona / strictness 取键 |

**不要**再向 `ws_handler.py` 叠加 mixin。新增能力应当:

1. 需要新状态时扩展 `ConnectionContext` 字段;
2. 在匹配的子包实现 mixin;
3. 经由既有栈(或 `turn/control.py`)聚合,不加深 MRO。

## 状态 SSOT

所有 mixin 经由 `self.ctx: ConnectionContext` 读写状态。**不要**在 mixin 上声明重复的宿主字段。

字段清单见 `core/context.py`;新增字段时保持该 dataclass 与本文档同步。

## 跨层依赖

`realtime`、`routes` 与 `process` 仅通过 `agents` 包门面(懒导出,如 `InterviewRunner`、`InterviewSessionState`、`run_finish_lifecycle`、`strip_markers`、`strip_think_blocks`)加两个叶子契约依赖 agent 执行链:`agents.events`(WS 事件契约,经 `schema_version` 版本化)与 `agents.agent_text`(纯文本过滤器)。禁止直接 import `agents` 的兄弟模块 — 门面是隔离内部重构(如拆分 runner)的接缝。

## 测试 patch 约定

realtime 测试 patch 所属模块的模块级符号(如 `turn.stt_finish.transcribe_utterance_result`、`voice.tts_queue.synthesize_speech`、`connection.heartbeat.verify_connection_lease`),而非 handler 类方法。

## 变更半径

轮次行为通常落在 `turn/` 与 `control/`;连接行为落在 `connection/`;音频路径落在 `voice/` 与 `engine/`。跨栈改动前,考虑将共享状态下沉到 `ConnectionContext` 或共享服务层。
