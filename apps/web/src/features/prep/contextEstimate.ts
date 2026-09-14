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

/** Reasoning/tool/search/status characters carried by one assistant message. */
export function assistantMetaChars(m: PrepChatMessage): number {
  let chars = textLen(m.statusText);
  const traceThinking = (m.trace ?? []).filter((i) => i.kind === "thinking");
  if (traceThinking.length > 0) {
    for (const item of traceThinking) chars += textLen(item.text);
  } else {
    chars += textLen(m.thinking);
  }
  for (const item of m.trace ?? []) {
    if (item.kind === "thinking") {
      continue;
    } else if (item.kind === "tool") {
      chars += textLen(item.name) + textLen(item.query);
      if (item.args) {
        for (const [k, v] of Object.entries(item.args)) chars += k.length + textLen(v);
      }
      chars += textLen(item.result);
    }
  }
  for (const step of m.steps ?? []) {
    chars += textLen(step.name) + textLen(step.query) + textLen(step.result);
    if (step.args) {
      for (const [k, v] of Object.entries(step.args)) chars += k.length + textLen(v);
    }
  }
  for (const group of m.searchGroups ?? []) {
    chars += textLen(group.query);
    for (const hit of group.results ?? []) {
      chars += textLen(hit.title) + textLen(hit.snippet);
    }
  }
  return chars;
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
  let total = estimateTextTokens(m.statusText);
  const traceThinking = (m.trace ?? []).filter((i) => i.kind === "thinking");
  if (traceThinking.length > 0) {
    for (const item of traceThinking) total += estimateTextTokens(item.text);
  } else {
    total += estimateTextTokens(m.thinking);
  }
  for (const item of m.trace ?? []) {
    if (item.kind === "thinking") {
      continue;
    } else if (item.kind === "tool") {
      total += estimateTextTokens(item.name) + estimateTextTokens(item.query);
      if (item.args) {
        for (const [k, v] of Object.entries(item.args)) total += estimateTextTokens(k) + estimateTextTokens(v);
      }
      total += estimateTextTokens(item.result);
    } else {
      total += item.after;
    }
  }
  for (const step of m.steps ?? []) {
    total += estimateTextTokens(step.name) + estimateTextTokens(step.query) + estimateTextTokens(step.result);
    if (step.args) {
      for (const [k, v] of Object.entries(step.args)) total += estimateTextTokens(k) + estimateTextTokens(v);
    }
  }
  for (const group of m.searchGroups ?? []) {
    total += estimateTextTokens(group.query);
    for (const hit of group.results ?? []) {
      total += estimateTextTokens(hit.title) + estimateTextTokens(hit.snippet);
    }
  }
  return total;
}
