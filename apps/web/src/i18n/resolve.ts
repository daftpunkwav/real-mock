/**
 * Translation resolve: locale lookup → fall back to default locale → on miss,
 * warn in development and return "ns.key" (never an empty string).
 * Interpolation supports ``{name}`` only.
 * Also holds the current locale for non-React callers (getTranslator/getLocale).
 */

import {
  DEFAULT_LOCALE,
  isLocaleId,
  type LocaleId,
} from "./locales";
import {
  messageCatalog,
  type MessageKey,
  type NamespaceId,
} from "./catalog";

export type TranslateValues = Record<string, string | number>;

export type Translator<N extends NamespaceId = NamespaceId> = {
  (key: MessageKey<N> | (string & {}), values?: TranslateValues): string;
  has(key: string): boolean;
};

let currentLocale: LocaleId = DEFAULT_LOCALE;

/** Active locale for non-React contexts; SSR / before init uses the default. */
export function getLocale(): LocaleId {
  return currentLocale;
}

/** LocaleProvider syncs the non-React current locale on mount and switch. */
export function setCurrentLocale(locale: LocaleId): void {
  if (isLocaleId(locale)) currentLocale = locale;
}

function interpolate(template: string, values: TranslateValues): string {
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    name in values ? String(values[name]) : match,
  );
}

/** Peek one message without interpolation (shared by tests and ``has``). */
export function peekMessage(locale: LocaleId, ns: NamespaceId, key: string): string | undefined {
  const table = messageCatalog[locale][ns] as Record<string, string>;
  const fallback = messageCatalog[DEFAULT_LOCALE][ns] as Record<string, string>;
  return table[key] ?? fallback[key];
}

export function createTranslator<N extends NamespaceId>(
  locale: LocaleId,
  ns: N,
): Translator<N> {
  // Defense: unregistered locale at runtime (e.g. hand-edited storage) falls back to default
  const active = isLocaleId(locale) ? locale : DEFAULT_LOCALE;
  const table = messageCatalog[active][ns] as Record<string, string>;
  const fallback = messageCatalog[DEFAULT_LOCALE][ns] as Record<string, string>;
  const translate = (key: string, values?: TranslateValues): string => {
    const template = table[key] ?? fallback[key];
    if (template === undefined) {
      if (process.env.NODE_ENV !== "production") {
        console.warn(`[i18n] missing message: ${ns}.${key} (${locale})`);
      }
      return `${ns}.${key}`;
    }
    return values ? interpolate(template, values) : template;
  };
  translate.has = (key: string): boolean => table[key] !== undefined;
  return translate as Translator<N>;
}

/** Translator for the current locale in non-React paths (error formatting, pure helpers). */
export function getTranslator<N extends NamespaceId>(ns: N): Translator<N> {
  return createTranslator(currentLocale, ns);
}
