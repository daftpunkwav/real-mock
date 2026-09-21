# Security Policy

## Supported versions

Security fixes land on `main` and are released in the latest tagged version (first release: `v0.1.0`). Older tags do not receive backports.

## Deployment model

RealMock is a local-first, single-user application. `scripts/dev.sh` binds the
backend to `127.0.0.1:8081`; the frontend dev server listens on port `8080`
and Next.js binds it to all interfaces by default, so keep it off untrusted
networks.
Model provider keys are user-supplied (BYOK) and stored encrypted at rest.
Exposing the backend beyond loopback (for example `--host 0.0.0.0`) is not a
supported configuration; the guards below mitigate but do not redesign that
deployment.

## Reporting a vulnerability

Report privately by email to **daftpunk.wav@outlook.com**. Please do not open
public issues for security reports.

Include a description of the issue, reproduction steps or a proof of concept,
the affected paths, and your assessment of severity. You will receive an
acknowledgment within 7 days and status updates while a fix is in progress.

## Security-relevant surfaces

In rough priority order (paths relative to the repository root):

- **Local exposure guards** — `apps/api/src/realmock/platform/core/local_only.py`:
  `LOCAL_API_DEPENDENCIES` (loopback check via `require_local_peer`, browser
  cross-site rejection, and same-origin enforcement on unsafe methods) is
  mounted on all seven domain routers (profile / resume / settings / interview /
  prep / records / growth); in `ENV=prod` the `TEST_MODE`
  escape hatch is ignored for non-loopback peers. The same module provides the
  mount-level cross-site guard (`Sec-Fetch-Site` and Origin/Referer checks,
  error `A0403`) applied to every service router, including WS handshakes.
- **SSRF guard** — `apps/api/src/realmock/platform/core/security/url.py` and
  `url_pin.py`: URL validation (private / CGNAT / multicast ranges, port
  allowlist, multi-record + IPv6 resolution) before any outbound request, plus
  DNS pinning (resolve once, connect to the fixed IP) to mitigate DNS-rebinding
  TOCTOU.
- **Snippet sandbox** —
  `apps/api/src/realmock/platform/capabilities/ai/agent/tools/isolation/`:
  agent code-execution isolation. `process.py` enforces wall-clock timeout,
  private working directory, and a scrubbed environment (default on Windows);
  `linux_job.py` adds an unprivileged user, a network namespace with no
  interfaces, and cgroup v2 memory/CPU caps. Controls that cannot be enforced
  are reported as explicit entries in `CompletedSnippet.notes`, never silently
  dropped.
- **Session authentication** —
  `apps/api/src/realmock/platform/core/session_auth/`: HttpOnly capability
  cookies per scope (`iv`, `prep`), constant-time token comparison, CSRF
  mitigation on the cookie-only path (Origin/Referer must be in the CORS
  allowlist), and rejection of query-string tokens in `ENV=prod` (cookie and
  header remain supported).
- **Secrets at rest** — `apps/api/src/realmock/platform/core/secrets.py`:
  AES-256-GCM authenticated encryption for stored provider keys
  (`enc:v2:...` format; key from the `SECRET_KEY` environment variable or
  `apps/api/src/realmock/platform/data/.secret.key`). `security/redact.py` redacts API-key-shaped strings
  from logs.
- **Upload safety** — `apps/api/src/realmock/platform/core/security/file.py`:
  filename sanitization (basename, character allowlist, length cap) and
  magic-number sniffing for accepted containers.
- **Frontend URL handling** —
  `apps/web/src/components/markdownComponents.tsx`: link `href` filtering for
  model-generated markdown (guarded by
  `apps/web/src/components/__tests__/markdownSafeUrl.test.ts`).

Findings outside the surfaces above are equally welcome. The architecture
guards in `apps/api/tests/architecture/` (layering, exposure regressions)
document the invariants these surfaces are held to.
