/**
 * @file contentKey.ts
 * @description Duplicate-safe list keys derived from row content (no array
 * indices): the content string and the occurrence counter are JSON-encoded
 * as a tuple, so a literal "a" and a generated "a#1" can never collide.
 * Render-only helper; keeps index-as-key linters satisfied without changing
 * list behavior.
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
    return { item, key: JSON.stringify([base, occurrence]) };
  });
}
