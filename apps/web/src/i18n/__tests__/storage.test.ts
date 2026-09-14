// @vitest-environment jsdom
/** Locale persistence: defaults, validation, and round trips. */

import { beforeEach, describe, expect, it } from "vitest";

import { DEFAULT_LOCALE } from "../locales";
import { LOCALE_STORAGE_KEY, readStoredLocale, writeStoredLocale } from "../storage";

describe("storage", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("returns the default locale when storage is empty", () => {
    expect(readStoredLocale()).toBe(DEFAULT_LOCALE);
  });

  it("rejects unsupported stored locales", () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, "fr-CA");
    expect(readStoredLocale()).toBe(DEFAULT_LOCALE);
  });

  it("round-trips supported locales", () => {
    writeStoredLocale("en");
    expect(readStoredLocale()).toBe("en");
    writeStoredLocale("zh-CN");
    expect(readStoredLocale()).toBe("zh-CN");
  });

  it("mirrors the locale into the cookie so the server can SSR it", () => {
    writeStoredLocale("en");
    expect(document.cookie).toContain(`${LOCALE_STORAGE_KEY}=en`);
    writeStoredLocale("zh-CN");
    expect(document.cookie).toContain(`${LOCALE_STORAGE_KEY}=zh-CN`);
  });
});
