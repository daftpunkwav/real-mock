// @vitest-environment node
/**
 * @file contentKey.test.ts
 * @description Content-derived keys must be unique even when item content
 * looks like a generated duplicate key (collision regression guard).
 */

import { describe, expect, it } from "vitest";

import { withContentKeys } from "../contentKey";

describe("withContentKeys", () => {
  it("keys all items uniquely, including duplicates", () => {
    const rows = withContentKeys(["a", "a", "b"], (x) => x);
    const keys = rows.map((r) => r.key);
    expect(new Set(keys).size).toBe(3);
    expect(rows.map((r) => r.item)).toEqual(["a", "a", "b"]);
  });

  it("does not collide when content looks like a generated key", () => {
    // ["a", "a", "a#1"]: the third item's content equals the second item's
    // generated key, so suffix-only encoding would collide.
    const rows = withContentKeys(["a", "a", "a#1"], (x) => x);
    const keys = rows.map((r) => r.key);
    expect(new Set(keys).size).toBe(3);
  });

  it("supports object rows via a content selector", () => {
    const rows = withContentKeys([{ q: "x" }, { q: "x" }], (item) => item.q);
    expect(new Set(rows.map((r) => r.key)).size).toBe(2);
  });
});
