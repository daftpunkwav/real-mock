# tests/ agent rules

The suite table lives in [README.md](README.md). This file is the working
rules for adding and changing tests.

## Placement

Placement mirrors ownership: domain behavior tests in `<domain>/`, platform
kernel in `platform_core/`, AI capabilities in `platform_ai/`, voice in
`voice/`, cross-cutting session-level integration in `sessions/`, guard
regressions in `architecture/`, aggregate boot smoke in `smoke/`. Keep a
domain's business logic in its own suite.

## Guards are the point

The suite runs green by default and CI treats it as blocking. Do not weaken,
skip, or xfail a guard to make a change pass — `architecture/`, the contract
sync test, and the phase SSOT test fail for real design decisions, which get
made explicitly (extend an allowlist deliberately) rather than silently.

## Conventions

- Shared doubles come from `fakes.py`, shared fixtures from `conftest.py`.
- Realtime tests patch module-level symbols in the owning module, not
  methods on the handler class (rationale in
  `src/realmock/domains/interview/realtime/README.md`).
- Run from `apps/api`: `python -m pytest` (`testpaths = tests`).
