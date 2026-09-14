"use client";

import { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize from "rehype-sanitize";
import { markdownComponents } from "./markdownComponents";

/**
 * Normalize model-output tables to avoid:
 * - Space/Tab-separated columns that fail to render
 * - Inter-row ``--- --- ---`` treated as horizontal rules / extra headers
 * - Inserting a separator before every data row
 */
export function normalizeLooseTables(src: string): string {
  if (!src) return src;
  // Never touch fenced code blocks (``` / ~~~): code may legitimately contain
  // pipes, dashes and double spaces (e.g. Python `a | b`, alignment). Only
  // normalize prose segments between fences.
  return splitFencedSegments(src)
    .map((seg) => (seg.fenced ? seg.text : normalizeProseTables(seg.text)))
    .join("\n");
}

function normalizeProseTables(src: string): string {
  // Drop junk separator lines (whole line is dashes/colons/pipes/whitespace), including --- and |---|---| forms
  const cleaned = src
    .split("\n")
    .filter((line) => !isJunkSeparatorLine(line))
    .join("\n");

  if (cleaned.includes("|")) {
    return ensureGfmTableSeparators(cleaned);
  }
  return convertLooseColumnBlocks(cleaned);
}

/**
 * Recover a message swallowed by an UNCLOSED trailing fence (a frequent model
 * typo: the fence opens and half the reply renders as one code block).
 * Only for FINAL content — while streaming, an unclosed fence is a normal
 * partial and must keep rendering as growing code.
 *
 * Conservative: the tail is reclaimed as markdown only when it shows at
 * least two DISTINCT markdown block structures (headings / hr / lists /
 * tables / quotes) across 3+ non-blank lines. Genuine code tails (even with
 * `##` comments or pipes) stay code.
 */
export function repairUnclosedFence(src: string): string {
  if (!src) return src;
  const lines = src.split("\n");
  let inFence = false;
  let fenceChar = "";
  let openerIndex = -1;
  for (let i = 0; i < lines.length; i += 1) {
    const m = (lines[i] ?? "").match(/^(\s{0,3})(`{3,}|~{3,})/);
    if (!m) continue;
    const ch = m[2]![0]!;
    if (!inFence) {
      inFence = true;
      fenceChar = ch;
      openerIndex = i;
    } else if (ch === fenceChar) {
      inFence = false;
      fenceChar = "";
      openerIndex = -1;
    }
  }
  if (!inFence || openerIndex < 0) return src;
  const tail = lines.slice(openerIndex + 1).filter((l) => l.trim() !== "");
  if (tail.length < 3) return src;
  const kinds = new Set<string>();
  for (const line of tail) {
    const t = line.trim();
    if (/^#{1,6}\s/.test(t)) kinds.add("heading");
    else if (/^(-{3,}|_{3,}|\*{3,})\s*$/.test(t)) kinds.add("hr");
    else if (/^([-*+]\s|\d{1,3}[.)]\s)/.test(t)) kinds.add("list");
    else if (/^\s*>/.test(line)) kinds.add("quote");
    else if (t.includes("|") && (t.startsWith("|") || /\|.+\|/.test(t))) kinds.add("table");
  }
  if (kinds.size < 2) return src;
  // Drop the stray opener: a bare ```/```lang line vanishes; an opener with
  // trailing prose keeps the prose (but a lone language tag is not content).
  const opener = (lines[openerIndex] ?? "").replace(/^(\s{0,3})(`{3,}|~{3,})/, "").trim();
  const kept = opener !== "" && !/^[A-Za-z0-9_+#-]+$/.test(opener) ? [opener] : [];
  return [...lines.slice(0, openerIndex), ...kept, ...lines.slice(openerIndex + 1)].join("\n");
}

interface FencedSegment {
  text: string;
  fenced: boolean;
}

/** Split markdown into fenced-code vs prose segments (fence lines stay with the code). */
function splitFencedSegments(src: string): FencedSegment[] {
  const lines = src.split("\n");
  const segs: FencedSegment[] = [];
  let buf: string[] = [];
  let inFence = false;
  let fenceChar = "";

  const flush = (fenced: boolean) => {
    if (buf.length > 0) {
      segs.push({ text: buf.join("\n"), fenced });
      buf = [];
    }
  };

  for (const line of lines) {
    const m = line.match(/^(\s{0,3})(`{3,}|~{3,})/);
    if (m) {
      const ch = m[2]![0]!;
      if (!inFence) {
        flush(false);
        inFence = true;
        fenceChar = ch;
        buf.push(line);
      } else if (ch === fenceChar) {
        buf.push(line);
        flush(true);
        inFence = false;
        fenceChar = "";
      } else {
        buf.push(line);
      }
    } else {
      buf.push(line);
    }
  }
  // Unclosed fence: treat the tail as code (safer than mangling it as a table).
  flush(inFence);
  return segs;
}

/** Whole line is only dashes/colons/pipes/whitespace → uninformative pseudo-separator */
function isJunkSeparatorLine(line: string): boolean {
  const t = line.trim();
  if (!t) return false;
  // --- or --- --- --- or |---|---| or | --- | --- |
  if (/^[\s|:\-]+$/.test(t) && /-/.test(t)) return true;
  return false;
}

function convertLooseColumnBlocks(src: string): string {
  const lines = src.split("\n");
  const out: string[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i] ?? "";
    const cols = splitLooseColumns(line);
    if (cols.length < 2 || isDashOnlyCells(cols)) {
      out.push(line);
      i += 1;
      continue;
    }

    const block: string[][] = [cols];
    let j = i + 1;
    while (j < lines.length) {
      const next = lines[j] ?? "";
      if (!next.trim()) break;
      if (isJunkSeparatorLine(next)) {
        j += 1; // skip inter-row ---, keep assembling the same table
        continue;
      }
      const nextCols = splitLooseColumns(next);
      if (nextCols.length < 2) break;
      if (isDashOnlyCells(nextCols)) {
        j += 1;
        continue;
      }
      if (Math.abs(nextCols.length - cols.length) > 1) break;
      block.push(nextCols);
      j += 1;
    }

    if (block.length >= 2) {
      const width = Math.max(...block.map((r) => r.length));
      const pad = (row: string[]) => {
        const r = [...row];
        while (r.length < width) r.push("");
        return r.slice(0, width);
      };
      const header = pad(block[0]!);
      out.push(`| ${header.join(" | ")} |`);
      // Emit the separator once
      out.push(`| ${header.map(() => "---").join(" | ")} |`);
      for (let k = 1; k < block.length; k += 1) {
        out.push(`| ${pad(block[k]!).join(" | ")} |`);
      }
      i = j;
      continue;
    }

    out.push(line);
    i += 1;
  }

  return out.join("\n");
}

function isDashOnlyCells(cols: string[]): boolean {
  return cols.length > 0 && cols.every((c) => /^:?-{1,}:?$/.test(c.trim()));
}

function splitLooseColumns(line: string): string[] {
  const t = line.trim();
  if (!t) return [];
  if (t.includes("\t")) {
    return t.split(/\t+/).map((c) => c.trim()).filter(Boolean);
  }
  if (/\s{2,}/.test(t)) {
    return t.split(/\s{2,}/).map((c) => c.trim()).filter(Boolean);
  }
  return [];
}

/**
 * For existing pipe tables: insert a --- separator only when the header is followed by a data row
 * with no separator yet. Do not insert between every data row.
 */
function ensureGfmTableSeparators(src: string): string {
  const lines = src.split("\n");
  const out: string[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i] ?? "";
    out.push(line);

    if (isPipeRow(line) && !isSeparatorRow(line)) {
      const next = lines[i + 1] ?? "";
      // Already valid GFM: header + separator
      if (isSeparatorRow(next)) {
        i += 1;
        continue;
      }
      // Header followed immediately by a data row → insert one separator
      if (isPipeRow(next) && !isSeparatorRow(next)) {
        const n = countPipeColumns(line);
        out.push(`| ${Array.from({ length: n }, () => "---").join(" | ")} |`);
        // Emit following contiguous pipe data rows as-is
        i += 1;
        while (i < lines.length) {
          const row = lines[i] ?? "";
          if (!isPipeRow(row) || isSeparatorRow(row)) break;
          // Skip junk separators sandwiched between data rows
          out.push(row);
          i += 1;
          // Skip leftover inter-row pseudo-separators (entry filter usually cleared these)
          while (i < lines.length && isJunkSeparatorLine(lines[i] ?? "")) {
            i += 1;
          }
        }
        continue;
      }
    }
    i += 1;
  }

  return out.join("\n");
}

function countPipeColumns(line: string): number {
  const parts = line.trim().split("|").map((p) => p.trim());
  // Drop empty segments produced by leading/trailing |
  const cells = parts.filter((p, idx) => {
    if (idx === 0 && p === "") return false;
    if (idx === parts.length - 1 && p === "") return false;
    return true;
  });
  return Math.max(cells.length, 1);
}

function isPipeRow(line: string): boolean {
  const t = line.trim();
  return t.includes("|") && (t.startsWith("|") || /\|.+\|/.test(t));
}

function isSeparatorRow(line: string): boolean {
  const t = line.trim();
  if (!t) return false;
  // | --- | :---: | ---: |
  if (/^\|?(\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$/.test(t)) return true;
  if (/^:?-{3,}:?(\s+|:?-{3,}:?)+$/.test(t)) return true;
  return false;
}

export function MarkdownContent({
  content,
  className = "",
  /**
   * True for settled content (history, finished streams). False while
   * streaming: an unclosed fence is then a normal partial, not an error.
   */
  final = true,
}: {
  content: string;
  className?: string;
  final?: boolean;
}) {
  const normalized = useMemo(
    () => normalizeLooseTables(final ? repairUnclosedFence(content) : content),
    [content, final],
  );

  return (
    <div className={`markdown-body text-sm min-w-0 max-w-full overflow-x-auto ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize]}
        components={markdownComponents}
      >
        {normalized}
      </ReactMarkdown>
    </div>
  );
}
