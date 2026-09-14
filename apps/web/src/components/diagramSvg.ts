/**
 * @file diagramSvg.ts
 * @description Pure helpers for rendering mermaid SVG output: error-diagram
 * detection, XSS defense-in-depth, and fluid sizing. Framework-free so the
 * diagram component stays thin and the logic is unit-testable in Node.
 */

/**
 * Mermaid resolves (instead of rejecting) with its built-in error diagram
 * when suppression is off; detect that SVG defensively so it is never shown
 * as a real diagram even if a future mermaid version changes the semantics.
 */
export function isErrorDiagramSvg(svg: string): boolean {
  if (svg.includes("Syntax error in text")) return true;
  // Match an actual error-icon ELEMENT. mermaid v12 ships an `.error-icon`
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
  return svg
    .replace(/<script[\s\S]*?<\/script\s*>/gi, "")
    .replace(/<foreignObject[\s\S]*?<\/foreignObject\s*>/gi, "")
    .replace(/<(embed|object|iframe|link|meta)\b[^>]*?(?:\/>|>[\s\S]*?<\/\1\s*>)/gi, "")
    .replace(/\s+on[a-z]+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, "")
    .replace(/\s+(?:href|xlink:href)\s*=\s*("|\')\s*javascript:[^"']*\1/gi, "")
    .replace(/\s+(?:href|xlink:href)\s*=\s*("|\')\s*data:text\/html[^"']*\1/gi, "");
}

/**
 * Repair LLM-generated flowchart `subgraph` headers that mermaid rejects.
 * Models often emit `subgraph 准备层 R["..."]` (bare CJK ids, spaces), but the
 * grammar only accepts a single ASCII id: `subgraph <id>["title"]`. Rewrite
 * invalid headers to generated ids while preserving the original wording as
 * the quoted title. Non-flowchart sources pass through untouched.
 */
export function repairMermaidSubgraphs(source: string): string {
  const lines = source.split("\n");
  const first = (lines[0] ?? "").trim().toLowerCase();
  if (!first.startsWith("flowchart") && !first.startsWith("graph")) {
    return source;
  }
  let counter = 0;
  let changed = false;
  const out = lines.map((line) => {
    const match = line.match(/^(\s*)subgraph\s+(.+?)\s*$/);
    if (!match) return line;
    const indent = match[1] ?? "";
    const header = (match[2] ?? "").trim();
    // Already valid: single ASCII id with an optional [title].
    if (/^[A-Za-z][A-Za-z0-9_]*(\[[^\n]*\])?$/.test(header)) return line;
    counter += 1;
    changed = true;
    // Split a trailing ["title"]: `准备层 R["简历结构化档案"]` keeps both
    // parts; same for unquoted `工作流A[工作流 A：技术深挖]`.
    const titled =
      header.match(/^(.*?)\[\s*"([^"\n]*)"\s*\]$/) ??
      header.match(/^(.*?)\[([^\[\]"\n]+)\]$/);
    const title = titled
      ? [titled[1]?.trim(), titled[2]?.trim()].filter(Boolean).join(" ")
      : header;
    const safe = title.replace(/"/g, "'").replace(/[\[\]]/g, "");
    return `${indent}subgraph sg${counter}["${safe}"]`;
  });
  return changed ? out.join("\n") : source;
}

/**
 * Make the diagram fluid: strip fixed width/height attributes mermaid emits
 * so the SVG scales with its container (zoom is applied by the wrapper).
 * Inputs without an svg root tag pass through untouched.
 */
export function fitDiagramSvg(svg: string): string {
  return svg.replace(/<svg\b([^>]*)>/, (_tag, attrs: string) => {
    const cleaned = String(attrs).replace(/\s+(width|height)="[^"]*"/gi, "");
    return `<svg${cleaned} width="100%" style="height:auto;max-width:100%;display:block;">`;
  });
}
