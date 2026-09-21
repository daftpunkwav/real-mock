# Contributing

RealMock is a personal, local-first project.
This guide describes how to develop it day-to-day and exactly what CI expects;
agent-specific working rules live in [AGENTS.md](AGENTS.md).

## Setup

- Backend: Python 3.12 (CI) / >=3.11 — `pip install -e ./apps/api`
- Frontend: Node 24 (see [.nvmrc](.nvmrc)) — `npm ci` inside `apps/web`
- One-command local dev: `scripts/dev.sh start|stop` (frontend on 8080, backend on 8081, logs and PIDs under `logs/`)

## Checks (local must match CI)

Run from `apps/api` unless noted:

| Gate | Command | Note |
|---|---|---|
| Lint | `python -m ruff check apps/api` | CI pins `ruff==0.15.20` |
| Types | `python -m mypy src` | CI pins `mypy==2.1.0`; blocking, must stay at 0 errors |
| Tests | `python -m pytest` | Coverage gate >=90% over the platform kernel and the profile / resume / settings / prep / interview domains in CI (records / growth are not measured) |
| Deps audit | `pip-audit --ignore-vuln PYSEC-2026-311` | chromadb issue with no upstream fix; declared in `pyproject.toml` |

Frontend, run from `apps/web`:

```bash
npx tsc --noEmit   # typecheck
npm run lint       # eslint
npm test           # vitest (coverage thresholds enforced from apps/web/vitest.config.mts)
npm run build      # production build
npm run audit      # dependency audit (fails on high+ unless allowlisted in npm-audit-allowlist.json)
```

## Contracts & generated files

The API contract chain is `scripts/export_openapi.py` -> `openapi.json` -> `apps/web/src/types/generated/api.d.ts`.
Regenerate with `npm run generate:api-types` (from `apps/web`); never hand-edit
generated artifacts. A guard test fails when the contract is stale. Pydantic
docstrings leak into schema descriptions — document schemas with `#` comments instead.

## Commit & branch conventions

- Commit: `<type>(<scope>): <subject>` with type `feat | fix | refactor | chore | docs | test | perf`
- Commits are in English and describe the change itself
- Branches: `<type>/<short-kebab-description>`, e.g. `feat/prep-agent-memory`

## Code rules

Enforced in review, backed by the architecture tests:

- Decoupling over cohesion: split mixed concerns even when a file is small; one responsibility per file
- Domains depend only on the platform kernel — no cross-domain business imports
- Neutral naming driven by function, boundary and responsibility
- Comments in English, explaining the code itself
- Minimal correct diffs; no speculative generality
- Type-only changes must have zero runtime footprint

## Security

Report vulnerabilities privately per [SECURITY.md](SECURITY.md) — do not open
public issues for them. The security-relevant surfaces and their guards are
listed there; changes to those paths deserve extra scrutiny in review.

## Docs

Every doc ships with a Chinese mirror (`<name>.zh.md`) kept current with the
code; a directory gets a README once its files stop being self-explanatory.
