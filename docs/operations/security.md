# Security

Mechanisms that exist in the code, per mechanism. All paths below are verified sources under `apps/api/src/realmock/platform/core/`. The mechanisms assume the deployment boundary the project states for itself: a local-first, single-user app that does not run on the public internet — no multi-user login, no multi-instance mechanisms exist in the code (`session_auth/__init__.py`), so each mechanism below applies within that single-process, loopback-oriented boundary.

## Loopback-only access (`local_only.py`)

| Guard | Behavior |
| --- | --- |
| `require_local_peer(request)` | Local management endpoints accept only loopback peers; non-loopback IPs are rejected with `A0405`. The Starlette `testclient` peer is always allowed; `TEST_MODE=1` permits real HTTP outside production only (ignored when `env=prod`). FastAPI cannot inject `Request` on WebSocket scopes, so WS endpoints call it with `request=None`, where it short-circuits — WS endpoints authenticate through session capability tokens instead. |
| `reject_cross_site_fetch(request)` | Rejects browser-driven cross-site requests (`Sec-Fetch-Site: cross-site`) with `A0403`. Non-browser clients (curl) do not send the header and pass. HTTP-only; `request=None` on WS scopes short-circuits. |
| `require_same_origin_for_writes(request)` | On unsafe methods (POST / PUT / PATCH / DELETE), `Origin` or `Referer` must be in the CORS allowlist, else `A0403`. Closes the gap `reject_cross_site_fetch` cannot: a page served from another localhost port is `same-site`, and body-less writes are CORS simple requests that skip preflight. Non-browser clients that send neither header pass. HTTP-only; `request=None` on WS scopes short-circuits. |
| `guard_ws_origin(websocket)` | Cross-site WS handshakes are closed before accept (close code 1008). Browsers always send `Origin`; hostnames must be `localhost` / loopback IPs; absent origin (non-browser) passes. |

`LOCAL_API_DEPENDENCIES` composes the three HTTP guards and is the single access-control truth mounted at router level; individual routers no longer declare their own.

## Session authentication (`session_auth/`)

Capability tokens per session — the local-first product has no multi-user login; mutating operations (WS / start / message / finish / messages / reports / prep) require the `access_token` issued at session creation.

| Module | Mechanism |
| --- | --- |
| `tokens.py` | `new_access_token()` — url-safe token with ~32 bytes of entropy (`secrets.token_urlsafe(32)`); `tokens_match()` constant-time comparison; `assert_session_token()` assertion helper. |
| `cookies.py` | HttpOnly cookies named `iv_{id}` / `prep_{id}` (scope `CookieScope = Literal["iv", "prep"]`), max age `COOKIE_MAX_AGE` = 90 days; `cookie_should_be_secure()` decides the Secure flag. |
| `extract.py` | HTTP extraction order: `X-Interview-Token` header > cookie > query; WebSocket extraction via the `mock.<token>` sub-protocol prefix. Production rejects query `?token=` (proxy / access-log leakage). On the cookie-only path, extraction calls the CSRF check. |
| `csrf.py` | `assert_csrf_if_cookie_only()` — Origin / Referer must match the CORS allowlist (`cors_origin_list`), as CSRF mitigation for cookie authentication. |

## Outbound request protection (`security/url.py`, `security/url_pin.py`)

SSRF filtering with DNS pinning, used by the agent `fetch` tool and the LLM clients:

- `_resolve_all()` resolves a hostname to every candidate IP (IPv4 + IPv6). A URL is rejected if **any** resolved address is unsafe.
- Default-blocked networks: loopback, link-local (`169.254.0.0/16`, metadata endpoints), private ranges, CGNAT, multicast, reserved, and IPv6 equivalents. `allow_local=True` additionally permits loopback only — private networks and metadata remain blocked.
- Port allowlist: only 80 / 443 by default (`_DEFAULT_ALLOWED_PORTS`); an explicit `allowed_ports` set is enforced regardless of `allow_local`.
- DNS-rebinding mitigation: `pin_safe_http_url()` resolves once, validates all candidates, and pins the first secure IP into a `PinnedHttpTarget`; `PinnedHostTransport` rewrites the request host to the pinned IP while keeping the `Host` header and SNI hostname; `make_pinned_async_client()` builds an `httpx.AsyncClient` with `follow_redirects=False`.
- Proxy fake-IP carve-out: `198.18.0.0/15` is always allowed, restricted to `FAKEIP_ALLOWED_HOSTS` (the `xiaomimimo.com` API hosts listed in `url.py`).
- The agent fetch tool follows redirects hop-by-hop: every hop builds a new pinned client (max 5 hops, `_MAX_REDIRECT_HOPS`), so the redirect target passes the same policy checks. The fetch tool itself fetches public pages only (loopback blocked), so model input cannot drive loopback management endpoints. The LLM clients validate `api_base` with `is_safe_http_url()` and send requests through pinned clients (`client/retry_stream.py`).

## Secrets at rest (`secrets.py`)

- AES-256-GCM authenticated encryption (`cryptography.hazmat.primitives.ciphers.aead.AESGCM`); random 16-byte salt and 12-byte nonce per ciphertext; the 32-byte AES key is derived per ciphertext from the master key with PBKDF2-HMAC-SHA256 (200,000 iterations).
- Ciphertext format `enc:v2:<b64-salt16>:<b64-nonce12>:<b64-tag16>:<b64-cipher>`.
- Master key source: the `SECRET_KEY` environment variable (base64 or plaintext, ≥16 bytes checked by `validate_master_key_env()`; the `asgi.py` startup gate `_check_secret_key_policy` enforces it when `env=prod`) or an auto-generated key file `data/.secret.key` (mode 0600).
- Old `enc:v1` ciphertexts raise `LegacySecretFormatError` — no silent migration; users re-save keys on the settings page. Unencrypted plaintext values pass through.
- Usage: provider channel API keys are encrypted on write (`apply_channel_key` in `domains/settings/services/model_registry.py`) and decrypted by `UnifiedLLMClient` (`decrypt_secret`).

## API key redaction (`security/redact.py`)

`redact_api_key()` prepares API keys for log output: PEM blocks become `***PEM_REDACTED***`; `Authorization` / `Bearer` / `Token` / `Basic` headers keep only the scheme; recognized key shapes (`sk-`, `sk-ant-`, Google `aiza` prefixes) and heuristically detected secrets (≥20 chars, letters + digits, no spaces) render as `first4***last4`. Callers include the LLM clients, STT providers, the platform logging setup (`core/logging.py`), and domain route / tool-guard error paths.

## File handling (`security/file.py`)

`sanitize_filename()` (ASCII-safe names, 120-char cap), `assert_within_dir()` (path-traversal containment), `sniff_extension()` (extension ↔ magic-number check for `pdf` / `docx` / `doc` containers).
