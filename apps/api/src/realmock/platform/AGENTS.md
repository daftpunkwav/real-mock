# platform/ agent rules

The package map lives in [README.md](README.md). This file is the working
rules for changes inside the kernel.

## Boundaries

- Platform never imports `realmock.domains` or `realmock.bootstrap` — the
  AST guard `tests/architecture/test_platform_no_domain_imports.py` fails on
  any edge. Domain behavior stays in the domains.
- Cross-domain event and data shapes live in `contracts/`; they define
  shapes and carry no business logic.
- Shared profile/resume tables are read by agent domains only through
  `services/candidate_read.py` — it is the sanctioned reader across the
  database split (guard:
  `tests/architecture/test_db_boundary_imports.py`).

## Adding capabilities

- Vendor-specific behavior belongs in vendor adapters and descriptors
  (`vendors/defs/`, `capabilities/voice/*/providers/`, the protocol
  translators under `capabilities/ai/llm/client/`), not in shared call
  paths. A vendor name branching inside shared code is the wrong layer.
- Isolation backends (`capabilities/ai/agent/tools/isolation/`) must report
  controls they cannot enforce as explicit `CompletedSnippet.notes` entries —
  silent downgrade is a contract violation (`base.py`).
- Security-relevant helpers live under `core/security/` and
  `core/session_auth/`; URL fetches go through the SSRF-checked pinned
  client (`core/security/url.py`), not raw `httpx`.

## Tests

Platform tests live in `apps/api/tests/platform_core/`, `platform_ai/`, and
`voice/`; cross-cutting session-level integration in `apps/api/tests/sessions/`.
