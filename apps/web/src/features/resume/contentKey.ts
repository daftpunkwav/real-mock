/**
 * @file contentKey.ts
 * @description Duplicate-safe list keys derived from row content (no array
 * indices): the first occurrence uses the raw content string, later
 * duplicates get a `#n` suffix. Render-only helper; keeps linters that
 * forbid index-as-key satisfied without changing list behavior.
 */

/** Pair each item with a unique, content-derived React key. */
export function withContentKeys<T>(
  items: readonly T[],
  content: (item: T) => string,
): { item: T; key: string }[] {
  const seen = new Map<string, number>();
  return items.map((item) => {
    const base = content(item);
    const occurrence = seen.get(base) ?? 0;
    seen.set(base, occurrence + 1);
    return { item, key: occurrence === 0 ? base : `${base}#${occurrence}` };
  });
}
