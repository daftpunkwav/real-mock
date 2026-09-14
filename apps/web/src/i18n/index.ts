/**
 * i18n public API barrel: app code imports only from here.
 * Do not depend on message internals or the low-level engine directly.
 */

export {
  DEFAULT_LOCALE,
  LOCALES,
  LOCALE_META,
  isLocaleId,
  type LocaleId,
  type LocaleMeta,
} from "./locales";
export { NAMESPACE_IDS, type NamespaceId, type MessageKey } from "./catalog";
export {
  createTranslator,
  getLocale,
  getTranslator,
  type Translator,
  type TranslateValues,
} from "./resolve";
export {
  formatDate,
  formatDateTime,
  formatNumber,
  formatTokenCount,
  type DateInput,
  type DateStyle,
} from "./format";
export { localizeApiError } from "./errors";
export { LocaleProvider } from "./LocaleProvider";
export { LocaleContext, useLocale, useT, type LocaleContextValue } from "./localeContext";
export { LocaleToggle } from "./LocaleToggle";
export { localeInitScript } from "./localeInitScript";
export { LOCALE_STORAGE_KEY } from "./storage";
