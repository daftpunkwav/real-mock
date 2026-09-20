# Interview WebSocket 协议

实时面试间在每个会话上运行一条 WebSocket。线上事件词汇表唯一收录于 [`protocol/interview_ws.schema.json`](../../protocol/interview_ws.schema.json)。

## 端点与握手

| 维度 | 行为 |
| --- | --- |
| URL | `/api/v1/ws/interview/{session_id}`（兼容别名 `/api/ws/interview/{session_id}`）；路由位于 `domains/interview/routes/ws/interview.py`，注册时不带域内前缀 |
| Origin 守卫 | `guard_ws_origin`（`platform/core/local_only.py`）在 accept 之前关闭浏览器发起的跨站握手，关闭码 `1008`；无 `Origin` 头的非浏览器客户端放行 |
| 能力令牌 | `extract_ws_token`（`platform/core/session_auth/extract.py`）按优先级解析会话令牌：cookie `iv_{session_id}` > 子协议 `mock.<token>` > query `token=`（生产环境忽略）；握手响应只回显来自客户端自身列表的 `mock.<token>` 子协议 |

## 帧格式

每条消息一个 JSON 对象，无信封：`{"type": "<事件类型>", ...payload}`（`realtime/connection/lifecycle.py: send()`）。

## SSOT 与守卫

- SSOT：`protocol/interview_ws.schema.json` — server / client 事件类型及逐事件 payload 结构。
- 后端：`realmock.domains.interview.constants` — `WSServerEvent`（20 个类型）与 `WSClientEvent`（15 个类型）。
- 前端：`apps/web/src/types/domains/interview_ws.ts`（`ServerEvent` / `ClientEvent` 联合类型）。
- 守卫：`apps/api/tests/interview/test_ws_protocol_schema.py` — 双向子集断言（后端枚举 ⊆ schema、前端联合类型 ⊆ schema）加逐事件 payload 覆盖检查。schema 刻意作为超集：`audio_chunk` 是保留的历史入站事件——派发器接受它，但第一方客户端不再发送（语音以 PCM 承载于 `user_turn_end` 内）。

## Server 事件（20 个）

| 事件 | 必填字段 | 可选字段 |
| --- | --- | --- |
| `turn_state` | `state`（`IDLE` \| `AI_SPEAKING` \| `USER_SPEAKING` \| `PROCESSING`） | |
| `assistant_token` | `token` | `phase` |
| `assistant_done` | `content`、`phase`、`is_complete` | `emotion`、`audio_b64`、`playback_generation`、`wait_seconds`、`answer_wait_seconds`、`sources`、`result`（`passed` \| `failed` \| null）、`phase_title` |
| `stt_partial` | `text` | |
| `stt_final` | `text` | |
| `tts_audio` | `data` | `mime`、`sentence`、`playback_generation` |
| `tts_failed` | `message` | |
| `tts_interrupted` | | `reason`、`candidate_interrupts`、`playback_generation` |
| `silence_nudge` | `content` | `seq`、`ai_interrupts` |
| `reference_hint_loading` | `question` | `detailed` |
| `reference_hint` | `content`、`question` | |
| `reference_hint_error` | `message`、`question` | |
| `phase_changed` | `phase` | `phase_title` |
| `interview_complete` | | `session_id`、`overall_score`、`result`（`passed` \| `failed` \| null） |
| `server_ping` | `t` | |
| `info` | `message` | `fallback`、`provider`、`requested_provider` |
| `error` | `message` | `code`、`retryable` |
| `coding_challenge_open` | `challenge` | |
| `coding_test_result` | `passed` | `test_results`、`stdout`、`stderr` |
| `coding_eval_report` | `report` | |

## Client 事件（15 个）

| 事件 | 必填字段 | 可选字段 |
| --- | --- | --- |
| `user_text` | `text` | `face_analysis`、`image_base64` |
| `user_turn_end` | `pcm`、`sample_rate` | `text`、`face_analysis`、`image_base64` |
| `stt_text` | `text` | |
| `user_typing` | | |
| `audio_chunk` | `data` |（保留的历史事件，第一方客户端不发送） |
| `silence_timeout` | | |
| `barge_in` | | |
| `request_hint` | `question` | |
| `request_finish` | | |
| `vision_update` | `face_analysis` | |
| `tts_playback_done` | | `generation` |
| `pong` | `t` | |
| `coding_code_update` | `code` | `language` |
| `coding_run_request` | `code` | `language` |
| `coding_submit_request` | `code` | `language`、`test_output` |

## 内部事件契约

| 模块 | 契约 |
| --- | --- |
| `domains/interview/agents/events.py` | `StreamEvent` / `EventKind`（`token` / `turn_done` / `error`）：runner → `ws_handler` 的流式契约；映射到线上事件 `assistant_token` / `assistant_done` / `error` |
| `domains/interview/realtime/core/events.py` | `SessionEvent.schema_version`（默认 `1`）：事件协议版本，事件协议变更时递增，供前端做兼容性检查；同一模块还定义 `turn_state` 使用的 `TurnState` 枚举 |
