# i18n/

Locale system (zh-CN / en).

| Module | Purpose |
| --- | --- |
| `LocaleProvider.tsx` / `localeContext.ts` | Locale state; document title is rendered here, not via `document.title` |
| `storage.ts` | Locale persistence (localStorage + cookie double write) |
| `locales.ts` / `resolve.ts` | Locale list and resolution; tests must resolve through `@/i18n/resolve`, not import `.tsx` directly |
| `catalog.ts` | Message catalog typing / lookup |
| `messages/` | Per-locale catalogs (`zh-CN/`, `en/`) — the only place user-visible prose may live |
| `errors.ts` | `NET`-family error-code → message mapping |
| `format.ts` | Locale-aware formatting helpers |
| `LocaleToggle.tsx` | Locale cycle toggle control |
| `localeInitScript.ts` | Pre-hydration locale bootstrap injected into the document |
