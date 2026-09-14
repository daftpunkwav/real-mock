/**
 * Prevent first-paint locale flash: sync <html lang> from storage before
 * hydration, and mirror the choice into a cookie so the server SSRs the same
 * locale on the next request. Injected into <head> by layout.
 */

import { DEFAULT_LOCALE, LOCALE_META } from "./locales";
import { LOCALE_STORAGE_KEY } from "./storage";

const HTML_LANG_BY_LOCALE: Record<string, string> = Object.fromEntries(
  Object.values(LOCALE_META).map((meta) => [meta.id, meta.htmlLang]),
);

export const localeInitScript = `(() => {
  try {
    var langs = ${JSON.stringify(HTML_LANG_BY_LOCALE)};
    var stored = localStorage.getItem(${JSON.stringify(LOCALE_STORAGE_KEY)});
    var locale = stored != null && langs[stored] ? stored : ${JSON.stringify(DEFAULT_LOCALE)};
    document.documentElement.lang = langs[locale];
    document.cookie = ${JSON.stringify(LOCALE_STORAGE_KEY)} + "=" + locale + "; path=/; max-age=31536000; samesite=lax";
  } catch (_) {}
})();`;
