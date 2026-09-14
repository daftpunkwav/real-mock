/** Locale preference persistence: localStorage for client reads + a cookie so the server can SSR the right locale. */

import { DEFAULT_LOCALE, isLocaleId, type LocaleId } from "./locales";

export const LOCALE_STORAGE_KEY = "realmock-locale";
const LOCALE_COOKIE_MAX_AGE = 31536000; // 1 year

function writeLocaleCookie(locale: LocaleId): void {
  document.cookie = `${LOCALE_STORAGE_KEY}=${locale}; path=/; max-age=${LOCALE_COOKIE_MAX_AGE}; samesite=lax`;
}

export function readStoredLocale(): LocaleId {
  try {
    const raw = localStorage.getItem(LOCALE_STORAGE_KEY);
    if (isLocaleId(raw)) return raw;
  } catch {
    /* ignore */
  }
  return DEFAULT_LOCALE;
}

export function writeStoredLocale(locale: LocaleId): void {
  try {
    localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  } catch {
    /* ignore */
  }
  writeLocaleCookie(locale);
}
