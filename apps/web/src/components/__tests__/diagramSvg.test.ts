/** Diagram SVG helpers: error detection, sanitizing, fluid sizing. */

import { describe, expect, it } from "vitest";

import { fitDiagramSvg, isErrorDiagramSvg, sanitizeDiagramSvg } from "../diagramSvg";

describe("isErrorDiagramSvg", () => {
  it("flags mermaid's error placeholder", () => {
    expect(isErrorDiagramSvg('<svg><g class="error-icon"/></svg>')).toBe(true);
    expect(isErrorDiagramSvg("<svg>Syntax error in text</svg>")).toBe(true);
  });

  it("passes real diagrams through", () => {
    expect(isErrorDiagramSvg('<svg viewBox="0 0 10 10"><g/></svg>')).toBe(false);
    expect(isErrorDiagramSvg("")).toBe(false);
  });

  it("ignores the .error-icon CSS rule shipped in every diagram stylesheet", () => {
    const healthy =
      '<svg id="a"><style>#a .error-icon{fill:#fff;}#a .error-text{fill:#000;}</style><g><rect/></g></svg>';
    expect(isErrorDiagramSvg(healthy)).toBe(false);
  });
});

describe("sanitizeDiagramSvg", () => {
  it("drops scripts and inline handlers, keeps shapes", () => {
    const dirty =
      '<svg onclick="evil()" width="10"><script>alert(1)</script><g onload=\'x\'><rect/></g></svg>';
    const clean = sanitizeDiagramSvg(dirty);
    expect(clean).not.toContain("<script");
    expect(clean).not.toContain("onclick");
    expect(clean).not.toContain("onload");
    expect(clean).toContain("<rect");
  });

  it("drops active embeds and javascript/data URLs, keeps safe links", () => {
    const dirty =
      '<svg><foreignObject><body>hi</body></foreignObject><embed src="x"/><a href="javascript:alert(1)">b</a><a href="https://example.com">ok</a></svg>';
    const clean = sanitizeDiagramSvg(dirty);
    expect(clean).not.toContain("foreignObject");
    expect(clean).not.toContain("<embed");
    expect(clean).not.toContain("javascript:");
    expect(clean).toContain("https://example.com");
  });

  it("drops script blocks whose closing tag carries attributes", () => {
    const dirty = '<svg><script src="x">alert(1)</script foo="bar"><rect/></svg>';
    expect(sanitizeDiagramSvg(dirty)).toBe("<svg><rect/></svg>");
  });

  it("removes spliced tags after nested-block removal until stable", () => {
    const dirty = "<svg><scr<script></script>ipt>alert(1)</scr</script>ipt></svg>";
    const clean = sanitizeDiagramSvg(dirty);
    expect(clean.toLowerCase()).not.toContain("<script");
    expect(clean).not.toContain("alert(1)</scr");
  });

  it("strips unclosed active tags and leftover script bodies", () => {
    const dirty = '<svg><script src="x">alert(1)<rect/></svg>';
    const clean = sanitizeDiagramSvg(dirty);
    expect(clean.toLowerCase()).not.toContain("<script");
    expect(clean).toContain("<rect");
  });

  it("strips inline handlers glued to a slash separator", () => {
    const dirty = '<svg><img src="x"/onload=alert(1)><rect/></svg>';
    const clean = sanitizeDiagramSvg(dirty);
    expect(clean).not.toContain("onload");
    expect(clean).toContain("<rect");
  });

  it("escapes stray active-tag openings without a closing bracket", () => {
    const dirty = "<svg><text>x</text><script";
    const clean = sanitizeDiagramSvg(dirty);
    expect(clean).not.toContain("<script");
    expect(clean).toContain("&lt;script");
  });
});

describe("fitDiagramSvg", () => {
  it("replaces fixed dimensions with fluid sizing", () => {
    const out = fitDiagramSvg('<svg width="640" height="480" viewBox="0 0 64 48"><g/></svg>');
    expect(out).toContain('width="100%"');
    expect(out).not.toMatch(/\sheight="/);
    expect(out).toContain("viewBox");
  });

  it("leaves non-svg input untouched", () => {
    expect(fitDiagramSvg("not svg")).toBe("not svg");
  });
});
