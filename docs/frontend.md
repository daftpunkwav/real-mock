# Frontend

Next.js + React app in `apps/web`. The dev server runs on port 8080 and stays in dev mode (`npm run dev`); a production build is only used by CI. Commands and the full source layout: [apps/web/README.md](../apps/web/README.md).

## Pages (`src/app/`)

One route segment per page.

| Segment | Page |
| --- | --- |
| `page.tsx` | Home |
| `profile/` | Candidate profile editor |
| `resume/` | Resume list / upload / review; `resume/preview/` serves the server-rendered preview page |
| `settings/` | Settings |
| `prep/` | Prep coach chat |
| `interview/` | Interview setup page (options, model bindings, multi-round toggle; `useInterviewSetup`) |
| `interview/[id]/` | Interview room |
| `report/[id]/` | Report view |
| `history/` | Interview history |
| `growth/` | Growth statistics |
| `avatar-debug/` | Avatar debugging page |

Shell files: `layout.tsx` (root layout), `error.tsx`, `loading.tsx`, `not-found.tsx`, `globals.css`.

## Feature modules (`src/features/`)

Feature-first business modules; each owns its components, hooks, and tests. Cross-feature pieces go up to `src/components/` and `src/lib/`. See [src/features/README.md](../apps/web/src/features/README.md).

| Feature | Purpose |
| --- | --- |
| `home/` | Landing page |
| `profile/` | Candidate profile editor |
| `resume/` | Resume upload, review, paginated preview |
| `settings/` | Settings pages (providers, models, stages, integrations) |
| `prep/` | Prep coach chat UI (composer, context panel, slash commands) |
| `interview/` | Interview room; the room hook assembly has its own README in `interview/hooks/room/` |
| `report/` | Report display (tabs, score formatting, live events) |
| `history/` | Interview history page |
| `growth/` | Growth statistics page |
| `media/` | Shared media primitives: mic recorder (`recorder/`), TTS player |
| `avatar/` | Interviewer avatar rendering (stage, portraits, scenes) |

## i18n (`src/i18n/`)

Locales are `zh-CN` and `en` (`locales.ts`); the product default is `en`.

| Module | Purpose |
| --- | --- |
| `LocaleProvider.tsx` / `localeContext.ts` | Locale state; the document title is rendered here as a React `<title>`, not via `document.title` |
| `storage.ts` | Locale persistence: localStorage for client reads plus a cookie so the server can SSR the right locale |
| `locales.ts` / `resolve.ts` | Locale list and resolution |
| `catalog.ts` | Message catalog typing / lookup |
| `messages/` | Per-locale catalogs (`zh-CN/`, `en/`) — the only place user-visible prose may live |
| `errors.ts` | `ApiError` → localized copy; error codes hit the `errors` catalog |
| `format.ts` | Locale-aware formatting helpers |
| `LocaleToggle.tsx` | Locale cycle toggle control |
| `localeInitScript.ts` | Pre-hydration locale bootstrap injected into the document |

Error codes: the `A`-family entries mirror the backend `realmock/platform/core/errors.py` catalog; the `NET0000`–`NET0005` family plus `http_*` fallbacks cover the network layer and are frontend-owned.

## Static config (`src/config/`)

| File | Purpose |
| --- | --- |
| `nav.ts` | Navigation |
| `pageLayout.ts` | Page layout |
| `phases.ts` | Interview phase English labels; mirrors the backend `realmock.domains.interview.workflows` (PhaseDef) — `apps/api/tests/interview/test_phase_ssot.py` asserts the match, so phase ids are not edited by hand |
| `prepPrompts.ts` | Prep quick prompts |

## API contract types (`src/types/generated/`)

`api.d.ts` is generated from the backend OpenAPI contract. `npm run generate:api-types` runs `../../scripts/export_openapi.py`, then `openapi-typescript` against the root `openapi.json`. The file is not edited by hand.

## In-browser code execution (`src/lib/code-runner/`)

| Language | Engine |
| --- | --- |
| `python` | Skulpt (in-browser interpreter), vendored at `public/vendor/skulpt` (pinned 1.2.0, no CDN); runs are serialized because `Sk.configure` targets global state; `execLimit` bounds CPU and raises `TimeLimitError` |
| `javascript` | Snippet runs in a Blob Web Worker off the UI thread; source travels via `postMessage`, and a main-thread timer terminates the worker on timeout |
| `typescript` / `tsx` | sucrase strips types (loaded on demand via dynamic import), then execution delegates to the JavaScript worker; the `imports` transform lowers `import`/`export` to CJS shims |

`registry.ts` maps fence language ids to engines, with aliases `js` / `ts` / `py`; UI code asks `isRunnable` / `getRunner` only.

## Interview room runtime hooks (`src/features/interview/hooks/room/`)

`useInterviewRoom(sessionId)` is the sole page consumer; its return type `InterviewRoomModel` is the UI-contract SSOT.

| Sub-hook | Responsibility |
| --- | --- |
| `useInterviewRoomBootstrap` | Session metadata, history messages, phase restore |
| `useInterviewWS` | WebSocket connection and `TurnState` |
| `useInterviewRoomState` | UI state + ref container |
| `useInterviewRoomTtsBinding` | TTS playback and generation alignment |
| `useInterviewRoomSilenceTimer` | Silence timeout / nudge |
| `useInterviewRoomEvents` | WS server event handling |
| `useInterviewRoomActions` | User actions (send, wrap-up, barge-in) |
| `useInterviewRoomRecorderBridge` | Mic / recorder bridge |

Details and change-radius rules: [src/features/interview/hooks/room/README.md](../apps/web/src/features/interview/hooks/room/README.md).

## Media capture (`src/features/media/recorder/`)

Mic capture for the interview room: WebAudio capture loop, VAD / barge-in detection, PCM buffering, ASR-session plumbing. `useAudioRecorder.ts` owns the capture state machine; `recorderMediaGraph.ts` builds the `AudioContext` + `ScriptProcessor` graph; `recorderAudioFrame.ts` does per-frame VAD, barge-in detection, PCM capture, and silence commits. TTS playback lives one level up in `features/media/`.
