/** Interview-prep SSE events (REST contract SSOT is OpenAPI via `@/lib/api/contract`;
 *  SSE streams are not in OpenAPI — hand-written contract). */

import type { PrepSearchGroup, PrepToolStep } from "@/lib/api/contract";

/** Shared SSE error event (prep stream and interview WS). */
export interface SSEErrorEvent {
  type: "error";
  message: string;
  code?: string;
  retryable?: boolean;
}

/** One turn DELTA of LLM token usage (backend `usage` event); cache hit rate = cached_tokens / prompt_tokens. */
export interface PrepUsageStats {
  prompt_tokens: number;
  completion_tokens: number;
  cached_tokens: number;
}

/** Stable context-breakdown bucket keys (backend contract, GET .../context). */
export type PrepContextBucketKey =
  | "user"
  | "assistant"
  | "thinking"
  | "tools"
  | "system"
  | "memory"
  | "other";

/** Measured tokens of one context bucket (mechanical estimate). */
export interface PrepContextBucket {
  key: string;
  tokens: number;
}

/** Measured persisted-history breakdown plus provider session totals. */
export interface PrepContextBreakdown {
  buckets: PrepContextBucket[];
  total_estimate: number;
  prompt_tokens: number;
  completion_tokens: number;
  cached_tokens: number;
}

/** Result of the /compact management endpoint. */
export interface PrepCompactResult {
  message_count: number;
  summarized: boolean;
  estimate_before: number;
  estimate_after: number;
  reason: string;
  summary_text: string;
  summary_version: number;
  fork_point: number | null;
  backup_session_id: number | null;
  /** Backend message index where the verbatim tail starts (display archive cutoff). */
  kept_from: number | null;
  compaction_prompt_tokens: number;
  compaction_completion_tokens: number;
  compaction_latency_ms: number;
}

/** Compaction parameters shared by manual /compact and auto-compact. */
export interface PrepCompactParams {
  intensity?: "light" | "balanced" | "aggressive";
  directive?: string;
  retain?: number;
  backup?: boolean;
  expected_message_count?: number;
}

/** Live compaction event: turn-start auto-compact or agent-invoked mid-turn fold. */
export interface PrepCompactionEvent {
  before: number;
  after: number;
  summarized: boolean;
  prompt_tokens: number;
  completion_tokens: number;
  latency_ms: number;
}

export type AskUserSelection = "single" | "multi";
export type AskUserWidget = "options" | "slider" | "rating";

/** Scale parameters for slider/rating widgets (backend-validated). */
export interface AskUserScale {
  min?: number;
  max?: number;
  step?: number;
  unit?: string;
}

/** ask_user dialog payload: the model decides shape, free text is always offered. */
export interface AskUserDialog {
  question: string;
  options: string[];
  selection: AskUserSelection;
  widget: AskUserWidget;
  scale?: AskUserScale;
  /**
   * Additional questions when one dialog asks several (1-8 backend-side).
   * Absent on single-question dialogs, whose flat fields are authoritative;
   * when present, the flat fields mirror questions[0] for compatibility.
   */
  questions?: AskUserDialog[];
  allow_custom: boolean;
  /** Recommended auto-submit answer on UI timeout (options/slider only). */
  suggested: string | null;
}

export type PrepSSEEvent =
  | { type: "token"; content: string }
  | { type: "status"; text: string }
  | { type: "thinking"; content: string }
  | ({ type: "tool_step"; name: string; query: string } & Partial<Pick<PrepToolStep, "args" | "result">>)
  | { type: "search_results"; groups: PrepSearchGroup[] }
  | ({ type: "ask_user" } & Partial<AskUserDialog> & Pick<AskUserDialog, "question" | "options">)
  | PrepUsageStats & { type: "usage" }
  | (PrepCompactionEvent & { type: "compaction" })
  /** Terminal envelope: session-level estimate plus provider-reported session totals. */
  | {
      type: "done";
      token_usage: number;
      prompt_tokens?: number;
      completion_tokens?: number;
      cached_tokens?: number;
      prompt_tokens_estimated?: number;
      turn_id?: string;
      prefix_fingerprint?: string;
      message_count?: number;
    }
  | SSEErrorEvent;
