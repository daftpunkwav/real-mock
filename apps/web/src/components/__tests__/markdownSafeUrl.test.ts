/** Markdown link sanitizing: which hrefs reach the DOM. */

import { describe, expect, it } from "vitest";

import { safeAbsoluteHttpUrl, safeHttpUrl } from "../markdownSafeUrl";

describe("safeHttpUrl", () => {
  it("passes same-origin paths and in-page anchors through unchanged", () => {
    expect(safeHttpUrl("/resume/preview")).toBe("/resume/preview");
    expect(safeHttpUrl("#section-2")).toBe("#section-2");
  });

  it("keeps absolute links and leaves protocol-relative ones for the browser", () => {
    expect(safeHttpUrl("https://example.com/a")).toBe("https://example.com/a");
    expect(safeHttpUrl("HTTP://example.com/a")).toBe("http://example.com/a");
    expect(safeHttpUrl("//cdn.example.com/x.js")).toBe("//cdn.example.com/x.js");
  });

  it("rejects relative paths instead of resolving them against the parse base", () => {
    // "./notes.md" used to become https://example.invalid/notes.md — a dead link.
    expect(safeHttpUrl("./notes.md")).toBeNull();
    expect(safeHttpUrl("images/a.png")).toBeNull();
    expect(safeHttpUrl("../up.html")).toBeNull();
  });

  it("rejects non-http schemes and empty input", () => {
    expect(safeHttpUrl("javascript:alert(1)")).toBeNull();
    expect(safeHttpUrl("data:text/html,x")).toBeNull();
    expect(safeHttpUrl("mailto:a@example.com")).toBeNull();
    expect(safeHttpUrl("   ")).toBeNull();
    expect(safeHttpUrl(undefined)).toBeNull();
  });
});

describe("safeAbsoluteHttpUrl", () => {
  it("accepts only absolute http(s)", () => {
    expect(safeAbsoluteHttpUrl("https://example.com/a")).toBe("https://example.com/a");
    expect(safeAbsoluteHttpUrl("/a")).toBeNull();
    expect(safeAbsoluteHttpUrl("ftp://example.com")).toBeNull();
  });
});
