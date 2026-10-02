# Pull request

## What and why

<!-- One or two sentences: what changes and what problem it solves. -->

## How it was verified

<!-- Which local commands did you run? CI runs the same ones - see CONTRIBUTING.md. -->
- [ ] `python -m ruff check apps/api`
- [ ] `python -m mypy src` (from `apps/api`)
- [ ] `python -m pytest` (from `apps/api`, coverage gate >= 90%)
- [ ] `npx tsc --noEmit`
- [ ] `npm run lint`
- [ ] `npm test`
- [ ] `npm run build`
- [ ] `npm run audit`

## Contracts and generated files

- [ ] If I changed an API route, model, or settings schema, I regenerated `openapi.json`
      (`python scripts/export_openapi.py`) and committed the result. CI fails on drift.

## Notes for the reviewer

<!-- Anything non-obvious: trade-offs, follow-ups, areas you want scrutinised. -->