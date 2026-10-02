/** Message catalog parity across locales.
 *
 * A missing key never fails at runtime: resolve.ts silently falls back to the
 * default locale, so only a structural check can catch a locale drifting out
 * of sync (missing namespace, missing key, or a placeholder that exists in one
 * translation but not in the other - interpolation would render it literally).
 */

import { describe, expect, it } from "vitest";

import { DEFAULT_LOCALE } from "../locales";
import { messageCatalog } from "../catalog";

// The catalog's literal key types model lookups, not iteration; parity checks
// iterate over arbitrary locale/ns/key strings, so widen once at the boundary.
const catalog = messageCatalog as Record<string, Record<string, Record<string, string>>>;

const PLACEHOLDER = /\{(\w+)\}/g;

function keysOf(table: unknown): string[] {
  return Object.keys(table as Record<string, string>).sort();
}

function placeholdersOf(template: string): string[] {
  // Group 1 always matches (\w+), so the fallback never fires. Sorted because
  // the same placeholders may appear in a different order across translations.
  return [...template.matchAll(PLACEHOLDER)].map((match) => match[1] ?? "").sort();
}

describe("message catalog parity", () => {
  const locales = keysOf(catalog);
  const defaultNamespaces = keysOf(catalog[DEFAULT_LOCALE] ?? {});

  it("registers the same namespaces in every locale", () => {
    for (const locale of locales) {
      expect(keysOf(catalog[locale]), `${locale} namespaces`).toEqual(defaultNamespaces);
    }
  });

  it("exposes the same keys in every namespace of every locale", () => {
    for (const ns of defaultNamespaces) {
      const baseline = keysOf(catalog[DEFAULT_LOCALE]?.[ns] ?? {});
      for (const locale of locales) {
        if (locale === DEFAULT_LOCALE) continue;
        const table = catalog[locale]?.[ns] ?? {};
        const missing = baseline.filter((key) => !(key in table));
        const extra = Object.keys(table).filter((key) => !baseline.includes(key));
        expect(missing, `${locale}/${ns} missing keys`).toEqual([]);
        expect(extra, `${locale}/${ns} extra keys`).toEqual([]);
      }
    }
  });

  it("uses the same interpolation placeholders in every locale", () => {
    for (const ns of defaultNamespaces) {
      const baselineTable = catalog[DEFAULT_LOCALE]?.[ns] ?? {};
      for (const key of keysOf(baselineTable)) {
        const baseline = placeholdersOf(baselineTable[key] ?? "");
        for (const locale of locales) {
          if (locale === DEFAULT_LOCALE) continue;
          const table = catalog[locale]?.[ns] ?? {};
          const placeholders = key in table ? placeholdersOf(table[key] ?? "") : [];
          expect(placeholders, `${locale}/${ns}.${key} placeholders`).toEqual(baseline);
        }
      }
    }
  });
});
