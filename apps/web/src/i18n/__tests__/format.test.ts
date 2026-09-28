/** Locale-aware token, number, and date formatting. */

import { afterEach, describe, expect, it } from "vitest";

import { formatDate, formatDateTime, formatNumber, formatTokenCount, parseTimestamp } from "../format";
import { DEFAULT_LOCALE } from "../locales";
import { setCurrentLocale } from "../resolve";

describe("formatTokenCount", () => {
  afterEach(() => {
    setCurrentLocale(DEFAULT_LOCALE);
  });

  it("zh-CN: uses ten-thousand units above 10,000", () => {
    setCurrentLocale("zh-CN");
    expect(formatTokenCount(0)).toBe("0");
    expect(formatTokenCount(9999)).toBe("9999");
    expect(formatTokenCount(12345)).toBe("1.2万");
    expect(formatTokenCount(123456)).toBe("12.3万");
    expect(formatTokenCount(1234567)).toBe("123万");
  });

  it("en: uses K and M suffixes", () => {
    setCurrentLocale("en");
    expect(formatTokenCount(999)).toBe("999");
    expect(formatTokenCount(12345)).toBe("12.3K");
    expect(formatTokenCount(1234567)).toBe("1.2M");
    expect(formatTokenCount(2000000)).toBe("2M");
  });
});

describe("formatNumber", () => {
  afterEach(() => {
    setCurrentLocale(DEFAULT_LOCALE);
  });

  it("uses the active locale", () => {
    setCurrentLocale("en");
    expect(formatNumber(1234.5)).toBe("1,234.5");
  });
});

describe("date formatting", () => {
  it("returns Invalid Date for invalid input", () => {
    expect(() => formatDate(Number.NaN)).not.toThrow();
    expect(formatDate(Number.NaN)).toBe("Invalid Date");
    expect(formatDateTime("not-a-date")).toBe("Invalid Date");
  });
});

describe("parseTimestamp", () => {
  it("reads naive backend timestamps as UTC, not local time", () => {
    // The backend persists naive UTC (SQLite drops tzinfo); parsing it as
    // local time skewed every relative age by the UTC offset.
    expect(parseTimestamp("2026-09-28T16:00:00").getTime()).toBe(
      Date.UTC(2026, 8, 28, 16, 0, 0),
    );
    expect(parseTimestamp("2026-09-28 16:00:00.123456").getTime()).toBe(
      Date.UTC(2026, 8, 28, 16, 0, 0, 123),
    );
  });

  it("leaves explicit timezones and Date objects untouched", () => {
    expect(parseTimestamp("2026-09-28T16:00:00Z").getTime()).toBe(
      Date.UTC(2026, 8, 28, 16, 0, 0),
    );
    expect(parseTimestamp("2026-09-28T16:00:00+08:00").getTime()).toBe(
      Date.UTC(2026, 8, 28, 8, 0, 0),
    );
    const d = new Date();
    expect(parseTimestamp(d)).toBe(d);
  });
});
