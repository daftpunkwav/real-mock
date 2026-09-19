# config/

Static frontend configuration. Files hold keys and ids only — user-visible copy lives in the i18n catalogs.

| File | Purpose |
| --- | --- |
| `nav.ts` | Navigation items |
| `pageLayout.ts` | Per-page layout metadata |
| `phases.ts` | Interview phase ids / labels; mirrors the backend SSOT (`realmock.domains.interview.workflows`), guarded by `apps/api/tests/interview/test_phase_ssot.py` |
| `prepPrompts.ts` | Prep quick-prompt keys (copy in `i18n/messages/<locale>/prep.ts`) |
