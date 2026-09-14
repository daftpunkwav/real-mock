/**
 * @file previewIdentity.test.ts
 * @description Empty names must not invent a "?" avatar glyph.
 */

import { describe, expect, it } from "vitest";

import { avatarInitial, isPreviewFilled } from "../previewIdentity";

describe("avatarInitial", () => {
  it("returns empty when the name is blank or whitespace", () => {
    expect(avatarInitial("")).toBe("");
    expect(avatarInitial("   ")).toBe("");
  });

  it("returns the first visible character of a filled name", () => {
    expect(avatarInitial("Ada")).toBe("A");
    expect(avatarInitial(" 张三 ")).toBe("张");
  });

  it("returns the first code point, not the first UTF-16 unit", () => {
    // Astral-plane characters are a single code point: must not split into a lone surrogate.
    expect(avatarInitial("𝒜dam")).toBe("𝒜");
  });
});

describe("isPreviewFilled", () => {
  it("treats whitespace as empty", () => {
    expect(isPreviewFilled("")).toBe(false);
    expect(isPreviewFilled("  ")).toBe(false);
    expect(isPreviewFilled("Go")).toBe(true);
  });
});
