/** Pure output helpers: truncation and console-style formatting. */

import { describe, expect, it } from "vitest";

import { formatLogArgs, truncateText } from "../output";

describe("truncateText", () => {
  it("passes short text through untouched", () => {
    expect(truncateText("hello", 10)).toEqual({ text: "hello", truncated: false });
  });

  it("cuts at the cap and flags truncation", () => {
    expect(truncateText("hello world", 5)).toEqual({ text: "hello", truncated: true });
  });
});

describe("formatLogArgs", () => {
  it("prints strings verbatim and joins calls with spaces", () => {
    expect(formatLogArgs(["a", 1, true, null, undefined])).toBe("a 1 true null undefined");
  });

  it("serializes objects and arrays", () => {
    expect(formatLogArgs([{ x: 1 }, [1, 2]])).toBe(
      '{\n  "x": 1\n} [\n  1,\n  2\n]',
    );
  });

  it("degrades cycles instead of throwing", () => {
    const loop: Record<string, unknown> = {};
    loop.self = loop;
    expect(formatLogArgs([loop])).toContain("[Circular]");
  });

  it("formats errors and functions readably", () => {
    expect(formatLogArgs([new TypeError("boom")])).toBe("TypeError: boom");
    expect(formatLogArgs([function named() {}])).toBe("[Function named]");
  });

  it("never throws on hostile values", () => {
    const evil = {
      toJSON() {
        throw new Error("nope");
      },
      toString() {
        throw new Error("nope");
      },
    };
    expect(() => formatLogArgs([evil, 10n])).not.toThrow();
  });
});
