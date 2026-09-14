/**
 * ApiError → user-visible localized copy.
 * When ``code`` hits the errors catalog, use catalog text; if the catalog string still has
 * unfilled placeholders and params are missing, fall back to the server message
 * (short-term resilience so UI does not break).
 * Describe errors with a structural type here — do not import lib/api (keep lib → i18n).
 */

import { getTranslator } from "./resolve";
import type { TranslateValues } from "./resolve";

type ErrorLike = {
  code?: unknown;
  message?: unknown;
  hint?: unknown;
  params?: unknown;
};

function isErrorLike(error: unknown): error is ErrorLike {
  return typeof error === "object" && error !== null;
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/** Catalog text still containing {name} means params are required; otherwise fall back to server copy. */
function hasUnfilledPlaceholder(template: string): boolean {
  return /\{\w+\}/.test(template);
}

export function localizeApiError(error: unknown): string {
  if (!isErrorLike(error)) {
    return error instanceof Error ? error.message : String(error);
  }
  const serverMessage = asString(error.message) || (error instanceof Error ? error.message : "");
  const code = asString(error.code);
  const serverHint = asString(error.hint);
  if (!code) {
    return serverMessage || String(error);
  }

  const t = getTranslator("errors");
  const params: TranslateValues | undefined = isErrorLike(error.params)
    ? (error.params as TranslateValues)
    : undefined;

  let message = serverMessage;
  if (t.has(code)) {
    const template = t(code, params);
    if (!hasUnfilledPlaceholder(template) || params) {
      message = template;
    }
  }

  let hint = serverHint;
  const hintKey = `${code}.hint`;
  if (t.has(hintKey)) {
    const hintTemplate = t(hintKey, params);
    if (!hasUnfilledPlaceholder(hintTemplate) || params) {
      hint = hintTemplate;
    }
  }

  return `[${code}] ${message}${hint ? `\n${hint}` : ""}`;
}
