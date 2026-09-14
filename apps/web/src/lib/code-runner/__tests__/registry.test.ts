/** Runner registry: language mapping, aliases, and normalization. */

import { describe, expect, it } from "vitest";

import { getRunner, isRunnable, normalizeLanguageId } from "../registry";

describe("normalizeLanguageId", () => {
  it("maps aliases and tolerates case and whitespace", () => {
    expect(normalizeLanguageId("js")).toBe("javascript");
    expect(normalizeLanguageId("TS")).toBe("typescript");
    expect(normalizeLanguageId("  Py  ")).toBe("python");
    expect(normalizeLanguageId("go")).toBe("go");
    expect(normalizeLanguageId(undefined)).toBe("");
  });
});

describe("isRunnable / getRunner", () => {
  it("accepts python, javascript, and typescript families", () => {
    for (const lang of ["python", "py", "javascript", "js", "typescript", "ts", "tsx"]) {
      expect(isRunnable(lang)).toBe(true);
      expect(getRunner(lang)?.id).toBeTruthy();
    }
  });

  it("rejects copy-only languages and empty input", () => {
    for (const lang of ["go", "rust", "java", "bash", "json", "", undefined]) {
      expect(isRunnable(lang)).toBe(false);
      expect(getRunner(lang)).toBeUndefined();
    }
  });
});
