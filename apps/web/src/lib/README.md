# lib/

Framework-free utilities shared across features.

| Module / directory | Purpose |
| --- | --- |
| `api/` | HTTP client stack: request / SSE core (`apiRequest.ts`, `apiSse.ts`, `apiUrl.ts`, `apiError.ts`, `base.ts`) and per-domain clients (`*Http.ts`, `clients.ts`, `contract.ts`) |
| `code-runner/` | In-browser code execution: `pythonRunner.ts` (Skulpt), `javascriptRunner.ts` (Blob Worker), `typescriptRunner.ts` (type-stripping), plus `registry.ts` / `output.ts` / `types.ts` |
| `cnText.ts` | CJK text helpers (full-width punctuation normalization for legacy review data) |
| `thinkStream.ts` | Splits streaming content into thinking vs. final answer (`<think>` / `<thinking>` tag forms) |
| `interviewProcesses.ts` | Pure helpers for multi-round interview process continuation (no React / no API) |
| `compactThreshold.ts` | Prep compaction preferences (localStorage-backed: trigger, intensity, directive, retain window) |
| `canonicalHost.ts` | Pre-hydration script pinning the loopback host to 127.0.0.1 (keeps host-bound cookies from orphaning sessions) |
| `askDialog.ts` / `askTimeout.ts` | ask_user dialog helpers: SSE event normalization, answer formatting, timeout handling |
| `clipboard.ts` / `download.ts` | Clipboard and file-download helpers |
| `llmDefaults.ts` / `scoreColor.ts` / `env.ts` / `utils.ts` | Small single-purpose helpers |
