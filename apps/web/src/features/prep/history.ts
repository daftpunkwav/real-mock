/**
 * @file history.ts
 * @description Prep history normalizers into chat messages.
 */

import type { PrepHistoryMessage, PrepSearchGroup, PrepToolStep } from "@/lib/api/contract";
import { normalizeAskDialog } from "@/lib/askDialog";
import type { PrepChatMessage, PrepTraceItem } from "./types";

/** Normalize raw tool steps; undefined when empty. */
export function normalizeSteps(raw: unknown): PrepToolStep[] | undefined {
  if (!Array.isArray(raw)) return undefined;
  const steps: PrepToolStep[] = [];
  for (const item of raw) {
    const s = item as PrepToolStep;
    if (!s || typeof s !== "object" || typeof s.name !== "string") continue;
    const step: PrepToolStep = {
      name: s.name,
      query: String(s.query ?? ""),
      result: typeof s.result === "string" ? s.result : "",
    };
    if (s.args && typeof s.args === "object" && !Array.isArray(s.args)) {
      step.args = Object.fromEntries(
        Object.entries(s.args as Record<string, unknown>).map(([k, v]) => [k, String(v ?? "")]),
      );
    }
    steps.push(step);
  }
  return steps.length > 0 ? steps : undefined;
}

/** Normalize raw search groups; undefined when empty. */
export function normalizeSearchGroups(raw: unknown): PrepSearchGroup[] | undefined {
  if (!Array.isArray(raw)) return undefined;
  const groups = raw
    .filter(
      (g): g is PrepSearchGroup =>
        !!g &&
        typeof g === "object" &&
        typeof (g as PrepSearchGroup).query === "string" &&
        Array.isArray((g as PrepSearchGroup).results),
    )
    .map((g) => ({ query: g.query, results: g.results }));
  return groups.length > 0 ? groups : undefined;
}

/** Normalize raw thinking text; undefined when blank. */
export function normalizeThinking(raw: unknown): string | undefined {
  if (typeof raw !== "string") return undefined;
  const text = raw.trim();
  return text || undefined;
}

/** Append a thinking delta: merge into the trailing thinking block when contiguous. */
export function appendTraceThinking(trace: PrepTraceItem[], chunk: string): PrepTraceItem[] {
  if (!chunk) return trace;
  const last = trace[trace.length - 1];
  if (last && last.kind === "thinking") {
    return [...trace.slice(0, -1), { kind: "thinking", text: last.text + chunk }];
  }
  return [...trace, { kind: "thinking", text: chunk }];
}

/** Append one tool step to the timeline. */
export function appendTraceTool(
  trace: PrepTraceItem[],
  step: { name: string; query: string; args?: Record<string, string>; result?: string },
): PrepTraceItem[] {
  return [
    ...trace,
    {
      kind: "tool",
      name: step.name,
      query: step.query ?? "",
      ...(step.args ? { args: step.args } : {}),
      ...(step.result ? { result: step.result } : {}),
    },
  ];
}

/** Rebuild a timeline for restored history (thinking block first, then steps). */
export function buildTraceFromParts(
  thinking: string | undefined,
  steps: PrepToolStep[] | undefined,
): PrepTraceItem[] | undefined {
  const trace: PrepTraceItem[] = [];
  if (thinking) trace.push({ kind: "thinking", text: thinking });
  for (const s of steps ?? []) {
    trace.push({
      kind: "tool",
      name: s.name,
      query: s.query ?? "",
      ...(s.args ? { args: s.args } : {}),
      ...(s.result ? { result: s.result } : {}),
    });
  }
  return trace.length > 0 ? trace : undefined;
}

/** Backend summary-block markers surfaced as compaction cards (never model input). */
export const COMPACTION_SUMMARY_MARKER = "[Conversation Minutes]";
const COMPACTION_DIGEST_MARKER = "[Context compression]";
const PROVENANCE_MARKER = "[provenance";

/** Provenance trailer fields parsed from a summary block. */
export interface CompactionProvenance {
  version: number;
  forkPoint: number | null;
  backupSessionId: number | null;
  before: number | null;
  after: number | null;
}

/** Split a persisted summary block into display text and provenance. */
export function parseSummaryBlock(content: string): { summary: string; provenance: CompactionProvenance } {
  const text = content ?? "";
  const start = text.lastIndexOf(PROVENANCE_MARKER);
  const provenance: CompactionProvenance = { version: 0, forkPoint: null, backupSessionId: null, before: null, after: null };
  let summary = text;
  if (start >= 0) {
    summary = text.slice(0, start).trim();
    const body = text.slice(start + PROVENANCE_MARKER.length).replace(/^\s+|\]+\s*$/g, "");
    for (const token of body.split(/\s+/)) {
      const eq = token.indexOf("=");
      if (eq < 0) continue;
      const key = token.slice(0, eq);
      const num = Number(token.slice(eq + 1));
      if (!Number.isInteger(num)) continue;
      if (key === "v") provenance.version = num;
      else if (key === "fork_point") provenance.forkPoint = num;
      else if (key === "backup_session") provenance.backupSessionId = num;
      else if (key === "before") provenance.before = num;
      else if (key === "after") provenance.after = num;
    }
  }
  return { summary, provenance };
}

/** Map history into user and assistant chat messages. */
export function mapHistoryMessages(
  list: PrepHistoryMessage[],
  nextId: (prefix: string) => string,
): PrepChatMessage[] {
  let backendIndex = 0;
  const out: PrepChatMessage[] = [];
  const rows = Array.isArray(list) ? list : [];
  // Compaction records render below every message (creation order, not fold
  // position): they describe the run that just finished, like a notice.
  const cards: PrepChatMessage[] = [];
  for (let i = 0; i < rows.length; i += 1) {
    const m = rows[i]!;
    const index = backendIndex;
    backendIndex += 1;
    // Compaction records surface as cards (editable/regenerable); every other
    // system block (memory index, lang hint, refs) stays hidden as before.
    if (m.role === "system" && typeof m.content === "string") {
      if (m.content.startsWith(COMPACTION_SUMMARY_MARKER)) {
        const { summary, provenance } = parseSummaryBlock(
          m.content.slice(COMPACTION_SUMMARY_MARKER.length).trim(),
        );
        cards.push({
          id: nextId("c"),
          role: "compaction",
          content: summary,
          compaction: {
            summary,
            version: provenance.version,
            forkPoint: provenance.forkPoint,
            backupSessionId: provenance.backupSessionId,
            before: provenance.before,
            after: provenance.after,
          },
          backendIndex: index,
        });
        continue;
      }
      if (m.content.startsWith(COMPACTION_DIGEST_MARKER)) {
        cards.push({
          id: nextId("c"),
          role: "compaction",
          content: m.content,
          compaction: {
            summary: m.content,
            version: 0,
            forkPoint: null,
            backupSessionId: null,
            before: null,
            after: null,
          },
          backendIndex: index,
        });
        continue;
      }
    }
    // Unknown roles and empty bodies are display-dropped (never rendered),
    // but backendIndex still advances above: indices must mirror server
    // positions for fork/retract/concurrency guards, not visible rows.
    if (!((m.role === "user" || m.role === "assistant") && m.content)) continue;
    const thinking = normalizeThinking(m.thinking);
    const steps = normalizeSteps(m.steps);
    const rawAsk = (m as { ask?: unknown }).ask;
    const msg: PrepChatMessage = {
      id: nextId(m.role === "user" ? "u" : "a"),
      role: m.role === "user" ? "user" : "assistant",
      content: String(m.content),
      steps,
      searchGroups: normalizeSearchGroups(m.search_groups),
      thinking,
      trace: buildTraceFromParts(thinking, steps),
      stopped: (m as { stopped?: unknown }).stopped === true ? true : undefined,
      ...(rawAsk && typeof rawAsk === "object" ? { ask: normalizeAskDialog(rawAsk as Record<string, unknown>) } : {}),
      backendIndex: index,
    };
    // An ask turn persists as TWO assistant rows: the loop tail (model answer,
    // ending in the ask_user tool call — or the inline-ask text) followed by
    // the display message (waiting line) that carries the turn's steps and
    // thinking. Live, they were one streaming bubble; merge them back so the
    // execution timeline renders on the content message instead of vanish-
    // ing from it. Consecutive content-bearing assistant rows only occur in
    // this shape.
    if (m.role === "assistant") {
      // Skip interleaved tool-result/system rows: the ask_user call leaves a
      // "dialog shown" tool row between the loop tail and the display message.
      let j = i + 1;
      while (j < rows.length && rows[j]!.role !== "user" && !(rows[j]!.role === "assistant" && rows[j]!.content)) {
        j += 1;
      }
      const next = rows[j];
      if (
        next &&
        next.role === "assistant" &&
        next.content &&
        (next.steps || next.thinking || next.ask) &&
        !msg.steps &&
        !msg.thinking &&
        !msg.ask
      ) {
        const nextThinking = normalizeThinking(next.thinking);
        const nextSteps = normalizeSteps(next.steps);
        msg.content = `${msg.content}\n\n${next.content}`;
        msg.steps = nextSteps;
        msg.thinking = nextThinking;
        msg.trace = buildTraceFromParts(nextThinking, nextSteps);
        const nextRawAsk = (next as { ask?: unknown }).ask;
        if (nextRawAsk && typeof nextRawAsk === "object") {
          msg.ask = normalizeAskDialog(nextRawAsk as Record<string, unknown>);
        }
        // The merged rows keep their server positions consumed.
        backendIndex += j - i;
        i = j;
      }
    }
    out.push(msg);
  }
  return [...out, ...cards];
}
