/**
 * @file diagramSource.ts
 * @description Pure repairs for the mermaid source text of a chart: the syntax
 * defects LLM output produces that mermaid's parser rejects outright, and the
 * preamble scan mermaid's own lexer implies. Framework-free so the diagram
 * component stays thin and the logic is unit-testable in Node.
 *
 * Responsibilities:
 * - Split a packed flowchart header onto its own line
 * - Rewrite invalid flowchart `subgraph` headers
 * - Locate the diagram declaration past a preamble mermaid accepts
 *
 * Constraints:
 * - This module must not render, parse, or touch rendered SVG; that boundary
 *   belongs to diagramSvg.ts.
 * - Every repair must return its input unchanged when it does not apply, so the
 *   caller's `fixed === source` guard can skip a pointless retry.
 */

/**
 * Drop a trailing CR so a CRLF line can be matched against the LF-only
 * patterns below. Mermaid normalizes line endings before lexing.
 */
function stripLineTerminator(line: string): string {
  return line.endsWith("\r") ? line.slice(0, -1) : line;
}

/**
 * A YAML frontmatter fence: `---` alone on its line, keeping its indent.
 * mermaid matches the closing fence at the indent of the opening one.
 */
const FRONTMATTER_FENCE = /^([^\S\r\n]*)---[^\S\r\n]*$/;

/**
 * Index of the last line of the `%%{ ... }%%` directive opening at `from`.
 * mermaid lexes a directive as everything up to the first `}%%`, so the
 * interior lines are directive text and never a diagram declaration. An
 * unclosed directive consumes the rest of the source, as mermaid's own
 * directive pattern does.
 */
function directiveEnd(lines: string[], from: number): number {
  for (let index = from; index < lines.length; index += 1) {
    if ((lines[index] ?? "").includes("}%%")) return index;
  }
  return lines.length - 1;
}

/**
 * Index of the line holding the diagram declaration, skipping the preamble
 * mermaid accepts in front of it: blank lines, `%%` comments, single- and
 * multi-line `%%{ ... }%%` directives, and a leading YAML frontmatter block.
 * Returns -1 when the source declares no diagram. Stopping at the first other
 * line keeps the body of a non-flowchart chart — where arbitrary prose may
 * appear — out of the repair path.
 */
function diagramDeclarationIndex(lines: string[]): number {
  let frontmatterIndent: string | null = null;
  for (let index = 0; index < lines.length; index += 1) {
    const text = stripLineTerminator(lines[index] ?? "");
    const trimmed = text.trim();
    const fence = text.match(FRONTMATTER_FENCE);
    if (frontmatterIndent !== null) {
      // Only a fence at the opening indent closes the block, so an indented
      // `---` inside a YAML block scalar cannot end it early.
      if (fence?.[1] === frontmatterIndent) frontmatterIndent = null;
      continue;
    }
    if (fence) {
      frontmatterIndent = fence[1] ?? "";
    } else if (trimmed.startsWith("%%{")) {
      index = directiveEnd(lines, index);
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
 * directive, comment, or frontmatter block does not skip the whole repair; the
 * preamble itself is left untouched because `%%` comments and YAML metadata
 * are never flowchart body. Non-flowchart sources pass through untouched.
 */
export function repairMermaidSubgraphs(source: string): string {
  const lines = source.split("\n");
  const declaration = diagramDeclarationIndex(lines);
  const head = (lines[declaration] ?? "").trim().toLowerCase();
  if (!head.startsWith("flowchart") && !head.startsWith("graph")) {
    return source;
  }
  let counter = 0;
  let changed = false;
  const out = lines.map((line, index) => {
    if (index < declaration) return line;
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
  const match = stripLineTerminator(raw).match(PACKED_FLOW_HEADER);
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
