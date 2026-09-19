# app/

Next.js App Router: one route segment per page.

| Segment | Page |
| --- | --- |
| `page.tsx` | Home |
| `profile/` | Candidate profile editor |
| `resume/` | Resume list / upload / review; `resume/preview/` serves the server-rendered preview page |
| `settings/` | Settings |
| `prep/` | Prep coach chat |
| `interview/[id]/` | Interview room |
| `report/[id]/` | Report view |
| `history/` | Interview history |
| `growth/` | Growth statistics |
| `avatar-debug/` | Avatar debugging page |

Shell files: `layout.tsx` (root layout), `error.tsx`, `loading.tsx`, `not-found.tsx`, `globals.css`.
