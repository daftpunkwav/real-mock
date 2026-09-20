# Interview WebSocket Protocol

The realtime interview room runs over a single WebSocket per session. The wire-level event vocabulary is defined once in [`protocol/interview_ws.schema.json`](../../protocol/interview_ws.schema.json).

## Endpoint and handshake

| Aspect | Behavior |
| --- | --- |
| URL | `/api/v1/ws/interview/{session_id}` (legacy alias `/api/ws/interview/{session_id}`); route in `domains/interview/routes/ws/interview.py`, registered without a domain prefix |
| Origin guard | `guard_ws_origin` (`platform/core/local_only.py`) closes browser-driven cross-site handshakes before accept with code `1008`; non-browser clients without an `Origin` header pass |
| Capability token | `extract_ws_token` (`platform/core/session_auth/extract.py`) resolves the session token in priority order: cookie `iv_{session_id}` > subprotocol `mock.<token>` > query `token=` (ignored in production); the handshake response echoes only a `mock.<token>` subprotocol taken from the client's own list |

## Frame format

One JSON object per message, no envelope: `{"type": "<event-type>", ...payload}` (`realtime/connection/lifecycle.py: send()`).

## SSOT and guards

- SSOT: `protocol/interview_ws.schema.json` — server / client event types plus per-event payload shapes.
- Backend: `realmock.domains.interview.constants` — `WSServerEvent` (20 types) and `WSClientEvent` (13 types).
- Frontend: `apps/web/src/types/domains/interview_ws.ts` (`ServerEvent` / `ClientEvent` union types).
- Guard: `apps/api/tests/interview/test_ws_protocol_schema.py` — subset assertions in both directions (backend enums ⊆ schema, frontend union ⊆ schema) plus per-event payload coverage for every event. The schema is deliberately a superset: `user_typing` is a frontend-only client event and has no backend enum member.

## Server events (20)

| Event | Required fields | Optional fields |
| --- | --- | --- |
| `turn_state` | `state` (`IDLE` \| `AI_SPEAKING` \| `USER_SPEAKING` \| `PROCESSING`) | |
| `assistant_token` | `token` | `phase` |
| `assistant_done` | `content`, `phase`, `is_complete` | `emotion`, `audio_b64`, `playback_generation`, `wait_seconds`, `answer_wait_seconds`, `sources`, `result` (`passed` \| `failed` \| null), `phase_title` |
| `stt_partial` | `text` | |
| `stt_final` | `text` | |
| `tts_audio` | `data` | `mime`, `sentence`, `playback_generation` |
| `tts_failed` | `message` | |
| `tts_interrupted` | | `reason`, `candidate_interrupts`, `playback_generation` |
| `silence_nudge` | `content` | `seq`, `ai_interrupts` |
| `reference_hint_loading` | `question` | `detailed` |
| `reference_hint` | `content`, `question` | |
| `reference_hint_error` | `message`, `question` | |
| `phase_changed` | `phase` | `phase_title` |
| `interview_complete` | | `session_id`, `overall_score`, `result` (`passed` \| `failed` \| null) |
| `server_ping` | `t` | |
| `info` | `message` | `fallback`, `provider`, `requested_provider` |
| `error` | `message` | `code`, `retryable` |
| `coding_challenge_open` | `challenge` | |
| `coding_test_result` | `passed` | `test_results`, `stdout`, `stderr` |
| `coding_eval_report` | `report` | |

## Client events (14)

| Event | Required fields | Optional fields |
| --- | --- | --- |
| `user_text` | `text` | `face_analysis`, `image_base64` |
| `user_turn_end` | `pcm`, `sample_rate` | `text`, `face_analysis`, `image_base64` |
| `stt_text` | `text` | |
| `user_typing` | | (frontend-only) |
| `silence_timeout` | | |
| `barge_in` | | |
| `request_hint` | `question` | |
| `request_finish` | | |
| `vision_update` | `face_analysis` | |
| `tts_playback_done` | | `generation` |
| `pong` | `t` | |
| `coding_code_update` | `code` | `language` |
| `coding_run_request` | `code` | `language` |
| `coding_submit_request` | `code` | `language`, `test_output` |

## Internal event contracts

| Module | Contract |
| --- | --- |
| `domains/interview/agents/events.py` | `StreamEvent` / `EventKind` (`token` / `turn_done` / `error`): the runner → `ws_handler` streaming contract; maps onto the `assistant_token` / `assistant_done` / `error` wire events |
| `domains/interview/realtime/core/events.py` | `SessionEvent.schema_version` (default `1`): the event protocol version, incremented whenever the event protocol changes so the frontend can run compatibility checks; the same module defines the `TurnState` enum used by `turn_state` |
