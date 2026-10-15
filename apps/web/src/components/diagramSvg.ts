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
 * Index of the line holding the diagram declaration, skipping the preamble
 * mermaid accepts in front of it: blank lines, `%%` directives and comments,
 * and a leading YAML frontmatter block. Returns -1 when the source declares no
 * diagram. Stopping at the first other line keeps the body of a non-flowchart
 * chart — where arbitrary prose may appear — out of the repair path.
 */
function diagramDeclarationIndex(lines: string[]): number {
  let inFrontmatter = false;
  for (let index = 0; index < lines.length; index += 1) {
    const trimmed = (lines[index] ?? "").trim();
    if (inFrontmatter) {
      if (trimmed === "---") inFrontmatter = false;
      continue;
    }
    if (trimmed === "---") {
      inFrontmatter = true;
    } else if (trimmed !== "" && !trimmed.startsWith("%%")) {
      return index;
    }
  }
  return -1;
}

/**
 * Repair LLM-generated flowchart `subgraph` headers that mermaid rejects.
 * Models often emit `subgraph 准备层 R["..."]` (bare CJK ids, spaces), but the
 * grammar only accepts a single ASCII id: `subgraph <id>["title"]`. Rewrite
 * invalid headers to generated ids while preserving the original wording as
 * the quoted title. The flowchart is located past any preamble, so a leading
 * directive, comment, or frontmatter block does not skip the whole repair.
 * Non-flowchart sources pass through untouched.
 */
export function repairMermaidSubgraphs(source: string): string {
  const lines = source.split("\n");
  const declaration = (lines[diagramDeclarationIndex(lines)] ?? "").trim().toLowerCase();
  if (!declaration.startsWith("flowchart") && !declaration.startsWith("graph")) {
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
      header.match(/^(.*?)\[\s*"([^"\n]*)"\s*\]$/) ?? header.match(/^(.*?)\[([^\[\]"\n]+)\]$/);
    const title = titled
      ? [titled[1]?.trim(), titled[2]?.trim()].filter(Boolean).join(" ")
      : header;
    const safe = title.replace(/"/g, "'").replace(/[\[\]]/g, "");
    return `${indent}subgraph sg${counter}["${safe}"]`;
  });
  return changed ? out.join("\n") : source;
}

/**
 * A flowchart header whose direction shares its line with the first node
 * statement (`flowchart TB A["..."] --> B["..."]`).
 */
const PACKED_FLOW_HEADER = /^(\s*(?:flowchart|graph)\s+(?:TB|TD|BT|RL|LR))\s+(\S.*)$/;

/**
 * Repair a flowchart header that packs the direction and the first node
 * statement onto a single line (`flowchart TB A["..."] --> B["..."]`). The
 * flowchart grammar requires a NEWLINE right after the direction, so mermaid
 * lexes the trailing statement as NODE_STRING and rejects the chart with
 * "Expecting 'NEWLINE', got 'NODE_STRING'". Models emit this form routinely;
 * moving the statement to its own line is the only change required — label
 * contents (CJK, `@`, `<br/>`) are never the trigger. Lowercase directions
 * are a separate lexical error mermaid rejects on its own.
 *
 * The declaration is located past any preamble, and the split re-attaches the
 * line's own terminator, so the source's line endings and its leading
 * directive, comment, or frontmatter block survive the repair unchanged.
 * Sources without a packed header are returned untouched, which keeps the
 * caller's no-op retry guard meaningful.
 */
export function repairMermaidFlowHeader(source: string): string {
  const lines = source.split("\n");
  const index = diagramDeclarationIndex(lines);
  if (index < 0) return source;
  const raw = lines[index] ?? "";
  // A CRLF source carries its terminator on the line itself; match the text
  // without it so both halves of the split can carry it again.
  const terminator = raw.endsWith("\r") ? "\r" : "";
  const match = (terminator ? raw.slice(0, -1) : raw).match(PACKED_FLOW_HEADER);
  if (!match) return source;
  return [
    ...lines.slice(0, index),
    `${match[1] ?? ""}${terminator}`,
    `${match[2] ?? ""}${terminator}`,
    ...lines.slice(index + 1),
  ].join("\n");
}

/**
 * Every syntax repair applied to a chart before it is re-rendered.
 *
 * The order is load-bearing: the packed header must be split first, because
 * both repairs only recognise a declaration on the first non-preamble line, and
 * a CJK subgraph header sitting on the packed header line is invisible to
 * repairMermaidSubgraphs until the split has moved it onto its own line.
 * Applying them the other way round leaves such a chart unrepaired, and the
 * caller falls back to the source view.
 */
export function repairMermaidSource(source: string): string {
  return repairMermaidSubgraphs(repairMermaidFlowHeader(source));
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
