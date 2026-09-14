"use client";

/**
 * Locale runtime Provider: preference R/W + document sync + title render.
 * Context and hooks live in localeContext.ts (for .ts module consumers).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { DEFAULT_LOCALE, LOCALES, LOCALE_META, type LocaleId } from "./locales";
import { readStoredLocale, writeStoredLocale } from "./storage";
import { createTranslator, setCurrentLocale } from "./resolve";
import { LocaleContext } from "./localeContext";

function applyDocumentLocale(locale: LocaleId) {
  document.documentElement.lang = LOCALE_META[locale].htmlLang;
}

export function LocaleProvider({
  children,
  initialLocale,
}: {
  children: React.ReactNode;
  /** SSR locale from the cookie; keeps the first server paint on the user's language. */
  initialLocale?: LocaleId;
}) {
  const [locale, setLocaleState] = useState<LocaleId>(initialLocale ?? DEFAULT_LOCALE);

  useEffect(() => {
    const stored = readStoredLocale();
    setCurrentLocale(stored);
    setLocaleState(stored);
    applyDocumentLocale(stored);
  }, []);

  const setLocale = useCallback((next: LocaleId) => {
    writeStoredLocale(next);
    setCurrentLocale(next);
    setLocaleState(next);
    applyDocumentLocale(next);
  }, []);

  const value = useMemo(
    () => ({ locale, setLocale, locales: LOCALES }),
    [locale, setLocale],
  );

  // Title is rendered by React (hoisted into <head>): imperative document.title
  // gets reset by the metadata mechanism after hydration back to the SSR default.
  const meta = createTranslator(locale, "meta");

  return (
    <LocaleContext.Provider value={value}>
      <title suppressHydrationWarning>{meta("app.title")}</title>
      {children}
    </LocaleContext.Provider>
  );
}
