# protocol/

Wire-level protocol schemas shared between backend and frontend.

| File | Purpose |
| --- | --- |
| `interview_ws.schema.json` | SSOT for the interview WebSocket event vocabulary (server / client event types and payloads). Kept aligned with `realmock.domains.interview.constants` on the backend and `apps/web/src/types/domains/interview_ws.ts` on the frontend; the backend test `tests/interview/test_ws_protocol_schema.py` guards the alignment |
