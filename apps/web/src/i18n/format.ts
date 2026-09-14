/**
 * Intl formatting helpers: dates / numbers / token counts, all using the active locale's intl tag.
 * Call sites should not hard-code "zh-CN" or unit suffixes; use these helpers instead.
 */

import { LOCALE_META } from "./locales";
import { getLocale } from "./resolve";

export type DateStyle = "short" | "medium" | "long";

export type DateInput = number | string | Date;

const DATE_OPTS: Record<DateStyle, Intl.DateTimeFormatOptions> = {
  short: { year: "numeric", month: "numeric", day: "numeric" },
  medium: { year: "numeric", month: "short", day: "numeric" },
  long: { year: "numeric", month: "long", day: "numeric", weekday: "long" },
};

const TIME_OPTS: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit" };

// DateTimeFormat construction is relatively expensive; cache by tag × purpose for list renders.
const formatterCache = new Map<string, Intl.DateTimeFormat>();

function getFormatter(tag: string, cacheKey: string, opts: Intl.DateTimeFormatOptions) {
  const key = `${tag}|${cacheKey}`;
  let formatter = formatterCache.get(key);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat(tag, opts);
    formatterCache.set(key, formatter);
  }
  return formatter;
}

function intlTag(): string {
  return LOCALE_META[getLocale()].intl;
}

function toDate(value: DateInput): Date {
  return value instanceof Date ? value : new Date(value);
}

function formatDateWith(value: DateInput, cacheKey: string, opts: Intl.DateTimeFormatOptions): string {
  const date = toDate(value);
  // Match native toLocaleString fallback: invalid input returns a marker string, does not throw
  if (Number.isNaN(date.getTime())) return "Invalid Date";
  return getFormatter(intlTag(), cacheKey, opts).format(date);
}

export function formatDate(value: DateInput, style: DateStyle = "medium"): string {
  return formatDateWith(value, `date.${style}`, DATE_OPTS[style]);
}

export function formatDateTime(value: DateInput, style: DateStyle = "medium"): string {
  return formatDateWith(value, `datetime.${style}`, { ...DATE_OPTS[style], ...TIME_OPTS });
}

export function formatNumber(value: number, opts?: Intl.NumberFormatOptions): string {
  return new Intl.NumberFormat(intlTag(), opts).format(value);
}

function trimUnit(value: number): string {
  const rounded = value.toFixed(1);
  return rounded.endsWith(".0") ? rounded.slice(0, -2) : rounded;
}

/**
 * Human-readable token counts: zh folds at >=10k with no decimals at >=1M; en uses K/M with up to one decimal.
 */
export function formatTokenCount(count: number): string {
  const locale = getLocale();
  if (locale === "zh-CN") {
    if (count < 10000) return String(count);
    return `${(count / 10000).toFixed(count >= 1000000 ? 0 : 1)}万`;
  }
  if (count >= 1000000) return `${trimUnit(count / 1000000)}M`;
  if (count >= 1000) return `${trimUnit(count / 1000)}K`;
  return String(count);
}
