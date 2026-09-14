# Interview room runtime hooks

## Assembly entry

`useInterviewRoom(sessionId)` is the sole page consumer; return type `InterviewRoomModel` is the UI-contract SSOT.

## Sub-hook responsibilities (assembly order)

| Hook | Responsibility |
| --- | --- |
| `useInterviewRoomBootstrap` | Session metadata, history messages, phase restore |
| `useInterviewWS` | WebSocket connection and `TurnState` |
| `useInterviewRoomState` | UI state + ref container |
| `useInterviewRoomTtsBinding` | TTS playback and generation alignment |
| `useInterviewRoomSilenceTimer` | Silence timeout / nudge |
| `useInterviewRoomEvents` | WS server event handling |
| `useInterviewRoomActions` | User actions (send, wrap-up, barge-in) |
| `useInterviewRoomRecorderBridge` | Mic / recorder bridge |

## Cross-hook data flow

- **State**: `useInterviewRoomState` `state` + `set` + `refs`
- **WS**: `send` / `on` from `useInterviewWS`; inject via `sendRef` into child hooks to avoid stale closures
- **Recorder**: `recorderRef` shared by actions and the recorder bridge

When adding UI behavior, prefer:

1. Decide which child hook owns it (do not pile logic into `useInterviewRoom`);
2. If a new ref is needed, add it to `useInterviewRoomState`;
3. Only expose fields on `InterviewRoomModel` when the page needs them.

## Change-radius goal

A single-scenario change (e.g. TTS, silence timer) should stay within 1–2 hook files.
