# RealMock web

Next.js + React frontend. The dev server runs on port 8080 and must stay in dev mode (`npm run dev`); a production build is not the supported way to run this app locally.

## Commands

| Command | Purpose |
| --- | --- |
| `npm run dev` | Start the dev server on port 8080 |
| `npm run build` | Production build (used by CI; local development runs `npm run dev`) |
| `npm run test` | Run vitest once |
| `npm run test:watch` | Run vitest in watch mode |
| `npm run lint` | ESLint |
| `npm run generate:api-types` | Regenerate `src/types/generated/api.d.ts` from the backend OpenAPI contract |

`generate:api-types` runs `../../scripts/export_openapi.py`, then `openapi-typescript` against the root `openapi.json`. Do not edit `src/types/generated/` by hand.

## Source layout (`src/`)

| Directory | Purpose |
| --- | --- |
| [`app/`](src/app/README.md) | Next.js App Router pages, one route segment per page |
| `features/` | Feature-first business modules (see [src/features/README.md](src/features/README.md)) |
| [`components/`](src/components/README.md) | Cross-feature presentational components |
| [`config/`](src/config/README.md) | Static frontend configuration (navigation, page layout, interview phases, prep quick prompts) |
| [`lib/`](src/lib/README.md) | Framework-free utilities: API client, code runner, compaction, clipboard, and friends |
| [`i18n/`](src/i18n/README.md) | Locale system (zh-CN / en): provider, catalogs, error-code mapping |
| [`types/`](src/types/README.md) | Shared types; `generated/` holds the OpenAPI-derived API types |

## Conventions

- All user-visible strings come from the i18n catalogs; hard-coded prose is a review failure.
- `config/phases.ts` mirrors the backend phase SSOT (`realmock.domains.interview.workflows`); the backend test `tests/interview/test_phase_ssot.py` keeps them aligned — phase ids are not edited by hand.
- Tests live in `__tests__/` next to the code they cover.
