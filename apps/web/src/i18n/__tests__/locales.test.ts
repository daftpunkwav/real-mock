/** Locale registry consistency and validation. */

import { describe, expect, it } from "vitest";

import { DEFAULT_LOCALE, LOCALES, LOCALE_META, isLocaleId } from "../locales";

describe("locales", () => {
  it("includes the default locale", () => {
    expect(LOCALES).toContain(DEFAULT_LOCALE);
  });

  it("keeps LOCALES and LOCALE_META in sync", () => {
    for (const id of LOCALES) {
      expect(LOCALE_META[id], `missing meta for ${id}`).toBeDefined();
    }
    expect(Object.keys(LOCALE_META).sort()).toEqual([...LOCALES].sort());
  });

  it("provides valid intl and htmlLang tags", () => {
    for (const meta of Object.values(LOCALE_META)) {
      expect(meta.nativeLabel.length).toBeGreaterThan(0);
      expect(meta.shortLabel.length).toBeGreaterThan(0);
      expect(meta.htmlLang).toMatch(/^[a-z]{2}(-[A-Za-z]{2})?$/);
      expect(meta.intl).toMatch(/^[a-z]{2}(-[A-Za-z]{2})?$/);
    }
  });

  it("validates locale identifiers", () => {
    expect(isLocaleId("en")).toBe(true);
    expect(isLocaleId("zh-CN")).toBe(true);
    expect(isLocaleId("fr")).toBe(false);
    expect(isLocaleId(42)).toBe(false);
    expect(isLocaleId(null)).toBe(false);
  });
});
