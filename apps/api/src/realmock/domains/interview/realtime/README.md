# Interview WebSocket realtime layer

## Assembly

`InterviewWSHandler` (`ws_handler.py`) is a **thin assembly shell** that composes behavior via mixin stacks:

| Stack | Modules | Responsibility |
| --- | --- | --- |
| ConnectionStack | `connection/auth`, `heartbeat`, `lifecycle` | Auth, heartbeat, connection lifecycle |
| TurnStack | `turn/coordinator` + `control` + `streaming` | Turn lock, STT/TTS streams, interrupt / closing |
| MediaStack | `voice/pipeline`, `voice/tts_queue`, `control/hint` | STT/TTS pipeline, sentence TTS, reference outline (`ReferenceHintMixin`) |
| MessageDispatcher | `core/message_dispatcher` | Client event dispatch |
| ReportScheduler | `report_scheduler` | Background report generation |

**Do not** stack more mixins onto `ws_handler.py`. New capabilities should:

1. Extend `ConnectionContext` fields when new state is needed;
2. Implement a mixin in the matching subpackage;
3. Aggregate through an existing stack without deepening the MRO.

## State SSOT

All mixins read/write state through `self.ctx: ConnectionContext`. **Do not** declare duplicate host fields on mixins.

See `core/context.py` for the field list; keep that dataclass and this document in sync when adding fields.

## Cross-layer dependencies

`realtime` and `routes` depend on the agent execution chain only through the
`agents` package facade (`InterviewRunner`, `InterviewSessionState`,
`run_finish_lifecycle`, `strip_markers`, `strip_think_blocks`) plus the event
contract (`agents.events`, versioned via `schema_version`). Never import
`agents` sibling modules directly — the facade is the seam that keeps
internal refactors (e.g. splitting the runner) from rippling outward.

## Test patch convention

Turn/STT tests should patch module-level symbols under `realmock.domains.interview.realtime.turn.coordinator.*`, not class methods.

## Change radius

Turn behavior usually touches `turn/` and `control/`; connection behavior touches `connection/`. Before cross-stack changes, consider sinking shared state into `ConnectionContext` or a shared service layer.
