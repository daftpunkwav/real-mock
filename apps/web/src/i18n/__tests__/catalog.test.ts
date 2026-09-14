/**
 * Catalog integrity checks:
 * 1) every locale exposes the same namespace keys
 * 2) English error copy matches the backend CATALOG.
 */

import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import { messageCatalog, NAMESPACE_IDS, type NamespaceId } from "../catalog";
import { LOCALES, type LocaleId } from "../locales";
import { PHASE_LABELS } from "../../config/phases";

/** Return a namespace table as a plain string record. */
function table(locale: LocaleId, ns: NamespaceId): Record<string, string> {
  return messageCatalog[locale][ns] as Record<string, string>;
}

const REFERENCE_LOCALE: LocaleId = "zh-CN";
const COMPARISON_LOCALES = LOCALES.filter((id) => id !== REFERENCE_LOCALE);

describe("catalog", () => {
  it("keeps locale key sets aligned with zh-CN", () => {
    for (const locale of COMPARISON_LOCALES) {
      for (const ns of NAMESPACE_IDS) {
        const referenceKeys = Object.keys(table(REFERENCE_LOCALE, ns)).sort();
        const localeKeys = Object.keys(table(locale, ns)).sort();
        expect(localeKeys, `namespace "${ns}" ${locale} key set differs from zh-CN`).toEqual(
          referenceKeys,
        );
      }
    }
  });

  it("contains only non-empty string values", () => {
    for (const locale of LOCALES) {
      for (const ns of NAMESPACE_IDS) {
        for (const [key, value] of Object.entries(table(locale, ns))) {
          expect(typeof value, `${locale}/${ns}/${key}`).toBe("string");
          expect(value.length, `${locale}/${ns}/${key}`).toBeGreaterThan(0);
        }
      }
    }
  });

  it("keeps interpolation placeholders aligned", () => {
    for (const locale of COMPARISON_LOCALES) {
      for (const ns of NAMESPACE_IDS) {
        for (const key of Object.keys(table(REFERENCE_LOCALE, ns))) {
          const referencePlaceholders = (
            (table(REFERENCE_LOCALE, ns)[key] ?? "").match(/\{\w+\}/g) ?? []
          ).sort();
          const localePlaceholders = ((table(locale, ns)[key] ?? "").match(/\{\w+\}/g) ?? []).sort();
          expect(localePlaceholders, `${ns}/${key} ${locale}`).toEqual(
            referencePlaceholders,
          );
        }
      }
    }
  });

  it("covers every configured phase in interview.phase.*", () => {
    const zhInterview = table(REFERENCE_LOCALE, "interview");
    for (const id of Object.keys(PHASE_LABELS)) {
      expect(zhInterview[`phase.${id}`], `interview.phase.${id}`).toBeDefined();
    }
  });
});

// ---------------------------------------------------------------------------
// Backend errors CATALOG parity (skip when the backend tree is unavailable)
// ---------------------------------------------------------------------------

const ERRORS_PY = resolve(
  __dirname,
  "../../../../../apps/api/src/realmock/platform/core/errors.py",
);

const hasBackendCatalog = existsSync(ERRORS_PY);

type PySpec = { code: string; message: string; hint: string };

/** Parse entries such as "A0001": ErrorSpec(...) from errors.py. */
function parseCatalog(source: string): PySpec[] {
  const specs: PySpec[] = [];
  const pattern =
    /"([ABC]\d{4})":\s*ErrorSpec\(\s*"([ABC]\d{4})",\s*\d+,\s*"((?:[^"\\]|\\.)*)"(?:,\s*"((?:[^"\\]|\\.)*)")?/g;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(source)) !== null) {
    const code = match[1];
    const message = match[3];
    if (!code || !message) continue;
    specs.push({ code, message, hint: match[4] ?? "" });
  }
  return specs;
}

describe.skipIf(!hasBackendCatalog)("errors × CATALOG", () => {
  const source = readFileSync(ERRORS_PY, "utf-8");
  const specs = parseCatalog(source);
  const zhErrors = table("zh-CN", "errors");
  const enErrors = table("en", "errors");

  it("parses backend CATALOG entries", () => {
    expect(specs.length).toBeGreaterThan(30);
  });

  it("contains every backend code in both locales", () => {
    for (const spec of specs) {
      expect(zhErrors[spec.code], `zh ${spec.code}`).toBeDefined();
      expect(enErrors[spec.code], `en ${spec.code}`).toBeDefined();
      expect(zhErrors[`${spec.code}.hint`], `zh ${spec.code}.hint`).toBeDefined();
      expect(enErrors[`${spec.code}.hint`], `en ${spec.code}.hint`).toBeDefined();
    }
  });

  it("en copy matches CATALOG verbatim (drift guard; CATALOG is English SSOT)", () => {
    for (const spec of specs) {
      expect(enErrors[spec.code], `${spec.code} message drifted`).toBe(spec.message);
      expect(enErrors[`${spec.code}.hint`], `${spec.code} hint drifted`).toBe(spec.hint);
    }
  });

  it("allows only NET#### and http_* frontend-only error codes", () => {
    const pyCodes = new Set(specs.map((s) => s.code));
    const extra = Object.keys(zhErrors)
      .map((key) => key.split(".")[0] ?? "")
      .filter(
        (code) =>
          !pyCodes.has(code) && !/^NET\d{4}$/.test(code) && !code.startsWith("http_"),
      );
    expect(extra, `errors catalog has codes missing from backend: ${extra.join(", ")}`).toEqual([]);
  });
});
