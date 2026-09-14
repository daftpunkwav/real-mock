"use client";

/**
 * Locale Context and hooks (kept apart from the Provider component so .ts modules
 * can consume them without pulling .tsx into the dependency graph — vitest cannot transform .tsx).
 */

import { createContext, useContext, useMemo } from "react";
import type { LocaleId } from "./locales";
import { createTranslator } from "./resolve";
import type { NamespaceId } from "./catalog";
import type { Translator } from "./resolve";

export type LocaleContextValue = {
  locale: LocaleId;
  setLocale: (locale: LocaleId) => void;
  locales: readonly LocaleId[];
};

export const LocaleContext = createContext<LocaleContextValue | null>(null);

export function useLocale() {
  const ctx = useContext(LocaleContext);
  if (!ctx) {
    throw new Error("useLocale must be used within LocaleProvider");
  }
  return ctx;
}

/** Component helper: translator bound to a namespace; new instance when locale changes to re-render. */
export function useT<N extends NamespaceId>(ns: N): Translator<N> {
  const { locale } = useLocale();
  return useMemo(() => createTranslator(locale, ns), [locale, ns]);
}
