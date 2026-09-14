/**
 * @file contextEstimate.ts
 * @description Measured context breakdown for the composer gauge.
 * User/reply buckets count message bodies; the system-and-tools bucket measures
 * reasoning/tool/search/status text that actually travels in context. Any
 * backend-known-but-unattributed remainder (server-side system prompt and tool
 * definitions) joins the system bucket so the breakdown always sums to `used`.
 */

import type { PrepChatMessage } from "./types";

/**
 * Characters per token by script — mirrors the backend estimator so the
 * gauge and the compaction budget agree: CJK text is token-dense, Latin is
 * sparse. A single blended ratio would over-estimate English sessions
 * (compacting too early) while fitting Chinese ones.
 */
export const PREP_EST_CJK_CHARS_PER_TOKEN = 1.5;
export const PREP_EST_LATIN_CHARS_PER_TOKEN = 4;
/** Fixed per-message framing cost (role tags, separators), same as backend. */
export const PREP_EST_MESSAGE_OVERHEAD = 4;

const CJK_RE = /[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af\uf900-\ufaff\uff00-\uffef]/;

/** Script-aware token estimate for one text (backend parity). */
export function estimateTextTokens(value: unknown): number {
  if (typeof value !== "string" || !value) return 0;
  let cjk = 0;
  // Code-point iteration; astral characters (emoji) fall into the Latin
  // bucket, which only makes the estimate slightly conservative.
  for (const ch of value) {
    if (CJK_RE.test(ch)) cjk += 1;
  }
  const latin = value.length - cjk;
  return Math.max(1, Math.floor(cjk / PREP_EST_CJK_CHARS_PER_TOKEN + latin / PREP_EST_LATIN_CHARS_PER_TOKEN));
}

export interface PrepContextEstimate {
  /** Estimated user-message tokens. */
  userEst: number;
  /** Estimated assistant-reply body tokens (body text only). */
  assistantEst: number;
  /**
   * Estimated system-and-tools tokens: measured reasoning/tool/search/status
   * text plus the unattributed remainder when the backend reports more.
   */
  systemEst: number;
  /** Measured total before reconciling with the backend report. */
  measuredTotal: number;
  /** Display total: backend report wins, measured estimate is the floor. */
  used: number;
}

function textLen(value: unknown): number {
  return typeof value === "string" ? value.length : 0;
}

/**
 * Shared trace/steps/search walker: thinking text (trace wins over the flat
 * field), tool calls, persisted steps, and search groups. The compaction
 * branch carries a post-compaction token count (`after`) instead of text, so
 * callers decide how to measure it via `onCompactionAfter`.
 */
function walkTraceMeta(
  m: PrepChatMessage,
  measure: (value: unknown) => number,
  onCompactionAfter: (after: number) => number,
): number {
  let total = measure(m.statusText);
  const traceThinking = (m.trace ?? []).filter((i) => i.kind === "thinking");
  if (traceThinking.length > 0) {
    for (const item of traceThinking) total += measure(item.text);
  } else {
    total += measure(m.thinking);
  }
  for (const item of m.trace ?? []) {
    if (item.kind === "thinking") {
      continue;
    } else if (item.kind === "tool") {
      total += measure(item.name) + measure(item.query);
      if (item.args) {
        for (const [k, v] of Object.entries(item.args)) total += measure(k) + measure(v);
      }
      total += measure(item.result);
    } else {
      total += onCompactionAfter(item.after);
    }
  }
  for (const step of m.steps ?? []) {
    total += measure(step.name) + measure(step.query) + measure(step.result);
    if (step.args) {
      for (const [k, v] of Object.entries(step.args)) total += measure(k) + measure(v);
    }
  }
  for (const group of m.searchGroups ?? []) {
    total += measure(group.query);
    for (const hit of group.results ?? []) {
      total += measure(hit.title) + measure(hit.snippet);
    }
  }
  return total;
}

/** Reasoning/tool/search/status characters carried by one assistant message. */
export function assistantMetaChars(m: PrepChatMessage): number {
  // Character picture has no token count for compaction events: the folded
  // text is gone, only the summary card remains (counted by the caller).
  return walkTraceMeta(m, textLen, () => 0);
}

/**
 * Estimate context usage from view-model messages.
 * Local-only messages (welcome banner, failed-turn error text) never entered
 * model context and are skipped. Stopped turns were persisted server-side
 * (stopped=True) and stay counted. Compaction cards count into the system
 * bucket (their summary block travels as a system message backend-side).
 * Per-message framing overhead mirrors the backend estimator.
 */
export function estimatePrepContext(
  messages: PrepChatMessage[],
  tokenUsage: number,
): PrepContextEstimate {
  let userEst = 0;
  let assistantEst = 0;
  let systemEst = 0;
  for (const m of messages) {
    if (m.localOnly) continue;
    if (m.role === "user") {
      userEst += estimateTextTokens(m.content);
      systemEst += PREP_EST_MESSAGE_OVERHEAD;
    } else if (m.role === "compaction") {
      systemEst += estimateTextTokens(m.content) + PREP_EST_MESSAGE_OVERHEAD;
    } else {
      assistantEst += estimateTextTokens(m.content);
      systemEst += metaTokens(m) + PREP_EST_MESSAGE_OVERHEAD;
    }
  }
  const measuredTotal = userEst + assistantEst + systemEst;
  const used = Math.max(tokenUsage || 0, Math.round(measuredTotal));
  // Server-side system prompt and tool definitions are invisible here; when
  // the backend reports more than we measured, attribute the remainder to the
  // system bucket instead of hiding it as ~0%.
  systemEst += Math.max(0, used - measuredTotal);
  return { userEst, assistantEst, systemEst, measuredTotal, used };
}

/** Token estimate of one assistant message's meta payload (thinking/tools/search). */
function metaTokens(m: PrepChatMessage): number {
  // Compaction events already carry a post-compaction token count (`after`,
  // measured when the fold ran); reuse it instead of re-estimating text that
  // no longer exists in context.
  return walkTraceMeta(m, estimateTextTokens, (after) => after);
}
