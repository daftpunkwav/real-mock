# domains/interview/ agent rules

The package map lives in [README.md](README.md); the realtime mixin rules in
[realtime/README.md](realtime/README.md). The seams below are enforced by
`apps/api/tests/architecture/test_interview_layering.py` — when one fails,
the change is wrong; extend an allowlist only as a deliberate, documented
decision.

## Dependency direction

`routes → realtime → agents → process`. The reverse edges are banned:

- `process/` never imports `agents/` — every LLM role lives under `agents/`.
- `agents/` never imports `realtime/` or `routes/`.

## The agents facade

- External layers (`realtime/`, `routes/`, `process/`) import `agents/` only
  through the package facade (`agents/__init__.py`) plus the two leaf
  contracts `agents.events` and `agents.agent_text` — never sibling modules.
- The facade's `__all__` must stay in sync with its `_LAZY_EXPORTS` map
  (tested); an export missing from either side fails the suite.

## The agents→process seam

Frozen to one allowlisted edge: `process.process_service` (the finish-path
subscriber). Shared stored-process documents (plan / round-plan / memory /
round chain) live in the neutral `protocols/` package that both `agents/`
and `process/` read — move shared code there instead of adding an edge.

## Realtime wiring

- `routes/` reaches `realtime/` only through `routes/ws/` →
  `realtime.ws_handler` (the single wire).
- Do not stack more mixins onto `ws_handler.py`; new state goes on
  `ConnectionContext`, new behavior into the matching subpackage aggregated
  by an existing stack (see `realtime/README.md`).

## Domain-wide

- The phase/workflow SSOT is `workflows.py`, locked against the frontend
  `src/config/phases.ts` by `tests/interview/test_phase_ssot.py`.
- The session ledger (`ledger/`) is written only by this domain.
