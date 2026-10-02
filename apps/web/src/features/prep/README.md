# features/prep/

Prep coach chat: sessions, the streaming send pipeline, and per-message actions.

## Entry and assembly

`usePrepChat` is the composition root and the only exported hook (`index.ts`;
pure helpers — history normalizers, context estimate, slash commands, "#"
session refs — and the stream registry are exported alongside it). It wires:

| Piece                                        | Responsibility                                                                                           |
| -------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `hooks/usePrepResources`                     | Resumes, sessions, model profiles                                                                        |
| `hooks/usePrepChatSession`                   | Restore / switch / create, history seeding, usage totals                                                 |
| `hooks/usePrepSend`                          | Send pipeline: per-session queue, streaming handlers, abort/stop, usage merge, backend-index booking     |
| `hooks/usePrepMessageActions`                | Export / fork / regenerate / retract / rate                                                              |
| `hooks/usePrepCompact`                       | Manual `/compact`, summary edits, archive of folded turns                                                |
| `hooks/usePrepSessionManage`                 | Delete / archive / restore / clear (stops the live stream first)                                         |
| `hooks/usePrepScroll`, `hooks/useTokenBatch` | Autoscroll follow, rAF token batching                                                                    |
| `streamRegistry.ts`                          | Module-level in-flight streams keyed by session id — they survive session switches and in-app navigation |

## Invariants

- `backendIndex` booking (user + assistant per fresh turn) backs fork /
  retract / regenerate; drift is healed from server truth (done envelope,
  message-list resync). Regenerate replaces the trailing user+assistant pair.
- Sends are refused while a manual compaction is in flight; folded turns stay
  visible via `compactionArchive.ts` (display-only, localStorage, per session).
- "#" session references attach history to one turn only; they never persist.
- AI quick-prompt suggestions refresh after each settled turn of the viewed
  session; an empty or failed refresh keeps the current card.
