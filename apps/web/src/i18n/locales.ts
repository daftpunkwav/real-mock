/** Locale registry: add a language by registering here and filling the messages tree. */

export const LOCALES = ["zh-CN", "en"] as const;
export type LocaleId = (typeof LOCALES)[number];

/** Product default language; used when storage is missing/invalid (no browser-language sniff). */
export const DEFAULT_LOCALE: LocaleId = "en";

export type LocaleMeta = {
  id: LocaleId;
  /** Self-name in that language for the switcher (e.g. Chinese / English); not translated with UI locale */
  nativeLabel: string;
  /** Abbreviation when the sidebar is collapsed */
  shortLabel: string;
  /** BCP 47 tag written to <html lang> */
  htmlLang: string;
  /** Tag passed to Intl.* */
  intl: string;
};

export const LOCALE_META: Record<LocaleId, LocaleMeta> = {
  "zh-CN": {
    id: "zh-CN",
    nativeLabel: "中文",
    shortLabel: "中",
    htmlLang: "zh-CN",
    intl: "zh-CN",
  },
  en: {
    id: "en",
    nativeLabel: "English",
    shortLabel: "En",
    htmlLang: "en",
    intl: "en-US",
  },
};

export function isLocaleId(value: unknown): value is LocaleId {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}
