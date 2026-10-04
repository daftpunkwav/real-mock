<!--
The PR title becomes the subject of the squashed merge commit:
  <type>(<scope>): <subject> — imperative, lowercase, ≤ 72 chars, no trailing period.

One PR does one thing; split unrelated changes. Merge requirements live in
the branch ruleset (2 approvals, threads resolved, up to date with main).
-->

## What

<!-- A few sentences: what changes? Lead with the behavior, not the file list. -->

## Why

<!-- The problem or motivation. Link the issue (`Closes #123`), or state why
     there is no issue: bug fixes and behavior changes need one; typos and
     doc corrections may skip it. -->

## How

<!-- What a reviewer should know: key decisions, alternatives considered and
     rejected, boundaries touched (domains, contracts, DB). Delete this
     section if the diff is self-explanatory. -->

## Verification

<!-- How you proved it works and did not break anything else. CI runs the
     same gates; local runs catch failures before the push. From `apps/api`
     unless noted. -->
- [ ] Tests added or updated — a bug fix ships a regression test that fails
      before the fix and passes after it
- [ ] `python -m ruff check apps/api` (repo root)
- [ ] `python -m mypy src` (blocking, must stay at 0 errors)
- [ ] `python -m pytest` (coverage gate ≥ 90% over the whole `realmock` package)
- [ ] `pip-audit --ignore-vuln PYSEC-2026-311 --ignore-vuln PYSEC-2026-3813 --ignore-vuln PYSEC-2026-3814 --ignore-vuln PYSEC-2026-3815`
- [ ] `npx tsc --noEmit` (apps/web)
- [ ] `npm run lint` · `npm test` · `npm run build` · `npm run audit` (apps/web)
- [ ] Anything the tests cannot reach was verified manually (describe below)

<!-- Manual steps, before/after output, screenshots. Delete if empty. -->

## Contracts and generated files

- [ ] If I changed an API route, model, or settings schema, I regenerated
      `openapi.json` (`python scripts/export_openapi.py`) and committed the
      result — CI fails on drift. Never hand-edit generated artifacts;
      document schemas with `#` comments, not docstrings.

## Compatibility impact

<!-- Public API, exported types, config, or stored-data format changes?
     "None" is a valid answer — state it explicitly. If breaking: what breaks,
     who is affected, and the migration path. -->

## Security and supply chain

<!-- Does the change touch authentication or trust boundaries, dependency
     manifests/lockfiles, or GitHub workflows? security.yml audits the
     dependencies on every PR regardless of paths — use this section to give
     the reviewer context the audits cannot infer. Otherwise write "N/A". -->

## Notes for the reviewer

<!-- Anything non-obvious: trade-offs, follow-ups, areas you want
     scrutinised. Delete if empty. -->
