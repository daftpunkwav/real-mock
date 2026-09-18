/**
 * Resolve & interpolate: locale lookup, {name} params, missing-key placeholder,
 * and non-React entry points.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_LOCALE } from "../locales";
import {
  createTranslator,
  getLocale,
  getTranslator,
  peekMessage,
  setCurrentLocale,
} from "../resolve";

describe("createTranslator", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    setCurrentLocale(DEFAULT_LOCALE);
  });

  it("returns copy for the requested locale", () => {
    const zh = createTranslator("zh-CN", "nav");
    const en = createTranslator("en", "nav");
    expect(zh("items.home")).toBe("首页");
    expect(en("items.home")).toBe("Home");
  });

  it("interpolates {name} with strings and numbers", () => {
    const t = createTranslator("zh-CN", "common");
    expect(t("request.failed", { status: 500 })).toBe("请求失败: 500");
    expect(t("theme.toggle.title", { label: "深色" })).toBe("切换到深色");
  });

  it("keeps unknown placeholders as-is", () => {
    const t = createTranslator("zh-CN", "common");
    expect(t("request.failed", { other: 1 })).toBe("请求失败: {status}");
  });

  it("missing key returns ns.key placeholder and warns in development", () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const t = createTranslator("zh-CN", "nav");
    expect(t("nope.missing")).toBe("nav.nope.missing");
    expect(warn).toHaveBeenCalledOnce();
    expect(warn.mock.calls[0]?.[0]).toContain("nav.nope.missing");
  });

  it("has only recognizes entries present in the current locale table", () => {
    const t = createTranslator("zh-CN", "nav");
    expect(t.has("items.home")).toBe(true);
    expect(t.has("nope")).toBe(false);
  });
});

describe("non-React entry points", () => {
  afterEach(() => {
    setCurrentLocale(DEFAULT_LOCALE);
  });

  it("getTranslator follows setCurrentLocale", () => {
    expect(getLocale()).toBe(DEFAULT_LOCALE);
    setCurrentLocale("en");
    expect(getTranslator("nav")("items.home")).toBe("Home");
  });

  it("setCurrentLocale rejects illegal values", () => {
    setCurrentLocale("fr" as never);
    expect(getLocale()).toBe(DEFAULT_LOCALE);
  });

  it("peekMessage parses a single entry without interpolation", () => {
    expect(peekMessage("zh-CN", "common", "request.failed")).toBe("请求失败: {status}");
  });

  it("falls back to the default locale for unregistered locales", () => {
    const t = createTranslator("fr" as never, "nav");
    expect(t("items.home")).toBe("Home");
  });
});
