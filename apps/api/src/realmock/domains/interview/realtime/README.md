# Interview WebSocket realtime layer

## Assembly

`InterviewWSHandler` (`ws_handler.py`) is a **thin assembly shell**: it composes three stack mixins from `stacks/` plus the dispatcher and the report scheduler.

| Piece | Modules | Responsibility |
| --- | --- | --- |
| ConnectionStack | `stacks/connection_stack` ← `connection/` (lifecycle, auth, heartbeat) | Connection lifecycle, auth, heartbeat, single-tab lease |
| TurnStack | `stacks/turn_stack` ← `turn/` (coordinator, streaming, control) | Turn lock and coordination, streaming, turn control |
| MediaStack | `stacks/media_stack` ← `voice/` (pipeline, tts_queue) + `control/hint` | STT/TTS pipeline, sentence TTS queue, reference outline |
| MessageDispatcher | `core/message_dispatcher` | Client event dispatch |
| ReportScheduler | `report_scheduler` | Background finish notify: freeze ledger via finish lifecycle + `interview_complete` push (debrief generation lives in the records domain) |

Supporting subpackages:

| Package | Purpose |
| --- | --- |
| `core/` | `context` (`ConnectionContext`, the state SSOT), `events`, `message_dispatcher`, `session_registry` (single-tab lease / takeover) |
| `control/` | Turn-control mixins (finish, interrupt, silence nudge / probe, turn timers, user text), aggregated by `turn/control.py` |
| `engine/` | Realtime audio engine abstraction: cascaded (STT → LLM → sentence TTS) vs. native full-duplex, with a factory |
| `nudge/` | Stateless silence-nudge templates keyed by phase / persona / strictness |

**Do not** stack more mixins onto `ws_handler.py`. New capabilities should:

1. Extend `ConnectionContext` fields when new state is needed;
2. Implement a mixin in the matching subpackage;
3. Aggregate through an existing stack (or `turn/control.py`) without deepening the MRO.

## State SSOT

All mixins read/write state through `self.ctx: ConnectionContext`. **Do not** declare duplicate host fields on mixins.

See `core/context.py` for the field list; keep that dataclass and this document in sync when adding fields.

## Cross-layer dependencies

`realtime`, `routes` and `process` depend on the agent execution chain only through the `agents` package facade (lazy re-exports such as `InterviewRunner`, `InterviewSessionState`, `run_finish_lifecycle`, `strip_markers`, `strip_think_blocks`) plus the two leaf contracts `agents.events` (WS event contract, versioned via `schema_version`) and `agents.agent_text` (pure text filters). Never import `agents` sibling modules directly — the facade is the seam that keeps internal refactors from rippling outward.

## Test patch convention

Realtime tests patch module-level symbols in the owning module (e.g. `turn.stt_finish.transcribe_utterance_result`, `voice.tts_queue.synthesize_speech`, `connection.heartbeat.verify_connection_lease`), not methods on the handler class.

## Change radius

Turn behavior usually touches `turn/` and `control/`; connection behavior touches `connection/`; the audio path touches `voice/` and `engine/`. Before cross-stack changes, consider sinking shared state into `ConnectionContext` or a shared service layer.
