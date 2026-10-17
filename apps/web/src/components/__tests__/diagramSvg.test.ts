/** Diagram SVG helpers: error detection, sanitizing, fluid sizing. */

import { describe, expect, it } from "vitest";

import {
  fitDiagramSvg,
  isErrorDiagramSvg,
  readSvgViewBox,
  sanitizeDiagramSvg,
} from "../diagramSvg";

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

describe("readSvgViewBox", () => {
  it("reads the intrinsic size from the root viewBox", () => {
    expect(readSvgViewBox('<svg viewBox="-8 -8 640 480"><g/></svg>')).toEqual({
      width: 640,
      height: 480,
    });
  });

  it("accepts the comma separated form and a viewBox on any attribute order", () => {
    expect(
      readSvgViewBox('<svg id="a" style="max-width:10px" viewBox="0,0,120,60"></svg>'),
    ).toEqual({
      width: 120,
      height: 60,
    });
  });

  it("returns null when there is no usable viewBox", () => {
    expect(readSvgViewBox('<svg width="10"></svg>')).toBeNull();
    expect(readSvgViewBox('<svg viewBox="0 0 0 480"></svg>')).toBeNull();
    expect(readSvgViewBox('<svg viewBox="a b c d"></svg>')).toBeNull();
    expect(readSvgViewBox('<svg viewBox="0 0 10"></svg>')).toBeNull();
    expect(readSvgViewBox("not svg")).toBeNull();
  });
});

describe("fitDiagramSvg", () => {
  it("hands the rendered size to the wrapper box", () => {
    const out = fitDiagramSvg('<svg width="640" height="480" viewBox="0 0 64 48"><g/></svg>');
    expect(out).toContain('style="display:block;width:100%;height:100%"');
    expect(out).not.toMatch(/\s(?:width|height)="/);
    expect(out).toContain("viewBox");
  });

  it("replaces mermaid's own style instead of appending a duplicate", () => {
    // A duplicate attribute is dropped by the HTML parser, so the original
    // max-width would keep capping the diagram and the new style would never
    // apply.
    const out = fitDiagramSvg('<svg style="max-width: 640px;" viewBox="0 0 64 48"><g/></svg>');
    expect(out).not.toContain("max-width");
    expect(out.match(/style="/g)).toHaveLength(1);
  });

  it("states the intrinsic ratio when a root gives pixels but no viewBox", () => {
    // Such an SVG is already one user unit per pixel, so this keeps that
    // mapping exact while giving the wrapper a ratio to scale against. Without
    // it the diagram stays a fixed-size image no zoom level can scale.
    const out = fitDiagramSvg('<svg width="640" height="480"><g/></svg>');
    expect(out).toContain('viewBox="0 0 640 480"');
    expect(out).toContain('style="display:block;width:100%;height:100%"');
    expect(out).not.toMatch(/\s(?:width|height)="/);
    expect(readSvgViewBox(out)).toEqual({ width: 640, height: 480 });
  });

  it("accepts unit suffixes on the synthesized viewBox", () => {
    expect(fitDiagramSvg('<svg width="640px" height="480px"><g/></svg>')).toContain(
      'viewBox="0 0 640 480"',
    );
  });

  it("leaves a root untouched when there is neither viewBox nor a usable size", () => {
    const degenerate = '<svg width="640" height="0"><g/></svg>';
    expect(fitDiagramSvg(degenerate)).toBe(degenerate);
    const bare = "<svg><g/></svg>";
    expect(fitDiagramSvg(bare)).toBe(bare);
  });

  it("leaves non-svg input untouched", () => {
    expect(fitDiagramSvg("not svg")).toBe("not svg");
  });
});
