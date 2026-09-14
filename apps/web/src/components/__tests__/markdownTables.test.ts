/** normalizeLooseTables: prose tables are fixed, fenced code is left byte-identical. */

import { describe, expect, it } from "vitest";

import { normalizeLooseTables } from "../MarkdownContent";

describe("normalizeLooseTables", () => {
  it("leaves python code containing pipes untouched", () => {
    const src = [
      "```python",
      "def bubble_sort(arr):",
      "    for i in range(n - 1, 0, -1):  # comment with | pipe",
      "        swapped = a | b",
      "        if arr[j] > arr[j + 1]:",
      "```",
    ].join("\n");
    expect(normalizeLooseTables(src)).toBe(src);
  });

  it("does not delete --- lines inside fenced code", () => {
    const src = ["```python", "x = 1", "---", "y = 2", "```"].join("\n");
    expect(normalizeLooseTables(src)).toBe(src);
  });

  it("still inserts a separator for a loose pipe table in prose", () => {
    const src = ["| a | b |", "| 1 | 2 |"].join("\n");
    expect(normalizeLooseTables(src)).toBe(
      ["| a | b |", "| --- | --- |", "| 1 | 2 |"].join("\n"),
    );
  });

  it("fixes prose tables while keeping an adjacent code fence intact", () => {
    const code = ["```python", "x = a | b", "```"].join("\n");
    const src = ["| a | b |", "| 1 | 2 |", "", code].join("\n");
    expect(normalizeLooseTables(src)).toBe(
      ["| a | b |", "| --- | --- |", "| 1 | 2 |", "", code].join("\n"),
    );
  });

  it("treats an unclosed fence tail as code", () => {
    const src = ["text", "```python", "x = a | b", "y  |  z"].join("\n");
    expect(normalizeLooseTables(src)).toBe(src);
  });
});
