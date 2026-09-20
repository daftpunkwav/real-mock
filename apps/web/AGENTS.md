# apps/web agent rules

The command/layout reference lives in [README.md](README.md); the check-gate
table lives in [../../CONTRIBUTING.md](../../CONTRIBUTING.md). This file is
only the working rules for editing the frontend.

## Dev mode is the local runtime

Local development runs `npm run dev` on port 8080. Do not verify frontend
work against `npm run build` output locally — a production server answering
200 is not evidence the dev behavior is correct.

## Generated and locked files

- `src/types/generated/api.d.ts` is generated from the backend OpenAPI
  contract. Never hand-edit it; after backend route changes regenerate it
  with `npm run generate:api-types` (the backend contract-sync test fails
  when `openapi.json` is stale).
- `src/config/phases.ts` mirrors the backend phase SSOT
  (`realmock.domains.interview.workflows`); the backend test
  `tests/interview/test_phase_ssot.py` fails on drift — phase ids are not
  edited by hand.

## i18n

`src/i18n/messages/` is the only place user-visible prose may live, with
`zh-CN/` and `en/` in lockstep — a key added to one must land in the other.
Hard-coded prose is a review failure. Page titles render through
`LocaleProvider`, never via `document.title`.

## Typecheck and tests

`npx tsc --noEmit` has no npm script — run it directly from `apps/web`.
Tests are colocated in `__tests__/` next to the code they cover.
