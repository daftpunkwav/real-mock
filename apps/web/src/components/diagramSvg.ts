/**
 * @file diagramSvg.ts
 * @description Pure helpers for processed mermaid SVG output: error-diagram
 * detection, XSS defense-in-depth, intrinsic-size extraction, and handing the
 * rendered size over to the viewport. Framework-free so the diagram component
 * stays thin and the logic is unit-testable in Node.
 *
 * Constraints:
 * - This module must not parse or repair mermaid source text; that boundary
 *   belongs to diagramSource.ts.
 */

/**
 * Mermaid resolves (instead of rejecting) with its built-in error diagram
 * when suppression is off; detect that SVG defensively so it is never shown
 * as a real diagram even if a future mermaid version changes the semantics.
 */
export function isErrorDiagramSvg(svg: string): boolean {
  if (svg.includes("Syntax error in text")) return true;
  // Match an actual error-icon ELEMENT. Mermaid ships an `.error-icon`
  // CSS rule inside every diagram's <style> block, so a bare substring
  // check misflags all healthy diagrams as failures.
  return /<[^>]*\bclass="[^"]*\berror-icon\b[^"]*"[^>]*>/.test(svg);
}

/**
 * Defense in depth under securityLevel strict: drop active elements
 * (script/foreignObject/embed/object/iframe/link/meta), inline event
 * handlers, and javascript:/data: URLs from generated SVG before injecting
 * it. Regex-based by design (no extra dependency for a second-layer filter);
 * the primary boundary is mermaid's own strict mode plus a same-origin,
 * non-navigable render container — this pass only shrinks the residue.
 */
export function sanitizeDiagramSvg(svg: string): string {
  const blockTag = /<(script|foreignObject)\b[^>]*>[\s\S]*?<\/\1\b[^>]*>/gi;
  // Closing tags may carry attributes (`</script foo>`), and removing one
  // nested block can splice leftover fragments into a fresh active tag
  // (`<scr<script>ipt>`), so the pass repeats until the text is stable.
  const loneTag = /<\/?(?:script|foreignObject|embed|object|iframe|link|meta)\b[^>]*>/gi;
  // The `on...=` name may directly follow `/` (`<img src=x/onload=...>`),
  // not only whitespace; the separator character is kept.
  const inlineHandler = /([\s/])on[a-z]+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]*)/gi;
  const activeUrl =
    /([\s/])(?:href|xlink:href)\s*=\s*(?:"\s*(?:javascript:|data:text\/html)[^"]*"|'\s*(?:javascript:|data:text\/html)[^']*')/gi;
  // A malformed tail can leave a bare active tag with no closing `>` for
  // the tag passes to catch; escaping the literal keeps the output free of
  // any active-tag substring (well-formed input never has one).
  const strayOpen = /<\/?((?:script|iframe|foreignObject|embed|object|link|meta)\b)/gi;
  // Rerun while any pass still has something to remove: removing a nested
  // block can splice leftover fragments into a fresh active tag
  // (`<scr<script>ipt>`). The condition is the disjunction of the pass
  // patterns themselves, so every iteration provably shrinks the text.
  const residue = new RegExp(
    [loneTag, inlineHandler, activeUrl, strayOpen].map((r) => `(?:${r.source})`).join("|"),
    "i",
  );
  let out = svg;
  while (residue.test(out)) {
    out = out
      .replace(blockTag, "")
      .replace(loneTag, "")
      .replace(inlineHandler, "$1")
      .replace(activeUrl, "$1")
      .replace(strayOpen, "&lt;$1");
  }
  return out;
}

/**
 * The diagram's intrinsic pixel size, taken from the root viewBox.
 *
 * The wrapper needs it to scale the diagram without measuring a laid-out SVG:
 * the viewBox is what mermaid lays the diagram out against, so it is the only
 * size that is stable before the element is in the document. Returns null when
 * the root carries no usable viewBox (no intrinsic ratio to scale against).
 */
export function readSvgViewBox(svg: string): { width: number; height: number } | null {
  // The grammar allows comma or whitespace separated values.
  const captured = /<svg\b[^>]*\bviewBox\s*=\s*"([^"]*)"/i.exec(svg)?.[1];
  if (captured === undefined) return null;
  const parts = captured
    .trim()
    .split(/[\s,]+/)
    .map(Number);
  const width = parts[2];
  const height = parts[3];
  if (
    parts.length !== 4 ||
    parts.some((part) => !Number.isFinite(part)) ||
    width === undefined ||
    height === undefined ||
    width <= 0 ||
    height <= 0
  ) {
    return null;
  }
  return { width, height };
}

/**
 * Hand the rendered size over to the wrapper: drop the fixed width/height and
 * the inline `style="max-width:Npx"` mermaid emits, then install exactly ONE
 * style attribute.
 *
 * Two details are load-bearing:
 * - The inline `max-width` mermaid adds caps the diagram at its natural size,
 *   which defeats any wrapper-driven scaling.
 * - A duplicate attribute is dropped by the HTML parser, so appending a second
 *   `style` next to mermaid's own leaves the original in force. The previous
 *   version did exactly that and its sizing never took effect.
 */
export function fitDiagramSvg(svg: string): string {
  return svg.replace(/<svg\b([^>]*)>/i, (_tag, attrs: string) => {
    const raw = String(attrs);
    const boxable = hasViewBox(raw) ? raw : synthesizeViewBox(raw);
    if (!boxable) return _tag;
    const cleaned = boxable
      .replace(/\s+(?:width|height)\s*=\s*"[^"]*"/gi, "")
      .replace(/\s+style\s*=\s*"[^"]*"/gi, "");
    return `<svg${cleaned} style="display:block;width:100%;height:100%">`;
  });
}

/** Whether the root already declares the ratio the wrapper scales against. */
function hasViewBox(attrs: string): boolean {
  return /\bviewBox\s*=\s*"[^"]*"/i.test(attrs);
}

/**
 * State as a viewBox the intrinsic ratio of a root that gives a pixel size
 * without one.
 *
 * Such an SVG is already one user unit per pixel, so `viewBox="0 0 w h"` keeps
 * that mapping exact while giving the wrapper the ratio it needs. Without it
 * the diagram stays a fixed-size image that no zoom level can scale, and the
 * viewport has no choice but to let it overflow its box.
 *
 * Returns null when there is no usable pixel size to derive it from.
 */
function synthesizeViewBox(attrs: string): string | null {
  const width = Number.parseFloat(/\swidth\s*=\s*"([^"]*)"/i.exec(attrs)?.[1] ?? "");
  const height = Number.parseFloat(/\sheight\s*=\s*"([^"]*)"/i.exec(attrs)?.[1] ?? "");
  if (!Number.isFinite(width) || !Number.isFinite(height)) return null;
  if (width <= 0 || height <= 0) return null;
  return `${attrs} viewBox="0 0 ${width} ${height}"`;
}
