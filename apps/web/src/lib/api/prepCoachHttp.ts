/**
 * @file prepCoachHttp.ts
 * @description Prep HTTP client: REST + SSE for the /v1/prep.* backend routes.
 * Named after the Prep Coach product surface; the backend package is `prep`.
 * A `prepHttp` alias is exported for call sites that prefer the short name.
 */

import type {
  PrepHistoryMessage,
  PrepSearchGroup,
  PrepSessionCreateResponse,
  PrepSessionSummary,
  PrepToolStep,
  ResumePickerItem,
} from "@/lib/api/contract";
import type { AskUserDialog, PrepCompactParams, PrepCompactResult, PrepContextBreakdown, PrepSSEEvent, PrepUsageStats, ReasoningEffort } from "@/types";
import { normalizeAskDialog } from "@/lib/askDialog";
import { ApiError, consumeSSE, parseStructuredErrorResponse, request, resolveBackendUrl, LLM_HEAVY_TIMEOUT_MS } from "@/lib/api/base";
import { getTranslator } from "@/i18n/resolve";

export interface PrepStreamCallbacks {
  onToken: (token: string) => void;
  onThinking?: (text: string) => void;
  onSearchResults?: (groups: PrepSearchGroup[]) => void;
  onStatus?: (text: string) => void;
  onToolStep?: (step: PrepToolStep) => void;
  onAskUser?: (dialog: AskUserDialog) => void;
  onUsage?: (usage: PrepUsageStats) => void;
  onCompaction?: (event: {
    before: number;
    after: number;
    summarized: boolean;
    prompt_tokens: number;
    completion_tokens: number;
    latency_ms: number;
  }) => void;
}

export const prepCoachHttp = {
  listResumes: () => request<ResumePickerItem[]>("/v1/prep/resumes"),
  listPrepSessions: () => request<PrepSessionSummary[]>("/v1/prep/sessions"),
  createPrepSession: (data: {
    resume_id?: number;
    target_role?: string;
    target_company?: string;
  }) =>
    request<PrepSessionCreateResponse>("/v1/prep/sessions", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  prepMessages: (sessionId: number) =>
    request<PrepHistoryMessage[]>(`/v1/prep/sessions/${sessionId}/messages`),
  contextBreakdown: (sessionId: number) =>
    request<PrepContextBreakdown>(`/v1/prep/sessions/${sessionId}/context`),
  compactSession: (sessionId: number, params?: PrepCompactParams) =>
    request<PrepCompactResult>(`/v1/prep/sessions/${sessionId}/compact`, {
      method: "POST",
      // Summarizer calls can take a while; never let the shared 30s budget kill one.
      timeoutMs: LLM_HEAVY_TIMEOUT_MS,
      body: params ? JSON.stringify(params) : undefined,
    }),
  updateSummary: (sessionId: number, text: string, expectedMessageCount?: number) =>
    request<PrepCompactResult>(`/v1/prep/sessions/${sessionId}/summary`, {
      method: "PATCH",
      timeoutMs: LLM_HEAVY_TIMEOUT_MS,
      body: JSON.stringify({
        text,
        ...(typeof expectedMessageCount === "number" ? { expected_message_count: expectedMessageCount } : {}),
      }),
    }),
  prepMessageStream: async (
    sessionId: number,
    content: string,
    callbacks: PrepStreamCallbacks,
    opts?: {
      modelProfileId?: number | null;
      reasoningEffort?: ReasoningEffort | null;
      dropLastAssistant?: boolean;
      uiLocale?: string;
      contextSessionIds?: number[];
      /** Auto-compact trigger as a fraction of the context window; omit for agent-decided. */
      compactThreshold?: number | null;
      compactIntensity?: "light" | "balanced" | "aggressive" | null;
      compactDirective?: string | null;
      compactRetain?: number | null;
      signal?: AbortSignal;
    },
  ): Promise<{
    token_usage: number;
    prompt_tokens: number;
    completion_tokens: number;
    cached_tokens: number;
    prompt_tokens_estimated: number;
    turn_id: string;
    prefix_fingerprint: string;
    message_count: number;
    usage: PrepUsageStats | null;
  }> => {
    const { onToken, onThinking, onSearchResults, onStatus, onToolStep, onAskUser, onUsage, onCompaction } = callbacks;
    const url = resolveBackendUrl(`/api/v1/prep/sessions/${sessionId}/message/stream`);
    // Idle watchdog: tool rounds emit events steadily, so a quiet stream is a
    // half-open connection, not a thinking model. No auto-reconnect: a turn is
    // non-idempotent (retrying would persist a duplicate turn server-side);
    // surface a stall error and let the user resend explicitly.
    const STREAM_IDLE_TIMEOUT_MS = 120_000;
    let lastActivity = Date.now();
    const touch = () => {
      lastActivity = Date.now();
    };
    let stalled = false;
    const watchdog = window.setInterval(() => {
      if (!stalled && Date.now() - lastActivity > STREAM_IDLE_TIMEOUT_MS) {
        stalled = true;
        internal.abort();
      }
    }, 5000);
    const internal = new AbortController();
    const forwardUserAbort = () => internal.abort();
    opts?.signal?.addEventListener("abort", forwardUserAbort, { once: true });
    let res: Response;
    try {
      res = await fetch(url, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        signal: internal.signal,
        body: JSON.stringify({
          content,
          model_profile_id: opts?.modelProfileId ?? undefined,
          reasoning_effort: opts?.reasoningEffort ?? undefined,
          drop_last_assistant: opts?.dropLastAssistant === true ? true : undefined,
          ui_locale: opts?.uiLocale || undefined,
          compact_threshold:
            typeof opts?.compactThreshold === "number" ? opts.compactThreshold : undefined,
          compact_intensity: opts?.compactIntensity ?? undefined,
          compact_directive: opts?.compactDirective || undefined,
          compact_retain: typeof opts?.compactRetain === "number" ? opts.compactRetain : undefined,
          context_session_ids:
            opts?.contextSessionIds && opts.contextSessionIds.length > 0
              ? opts.contextSessionIds
              : undefined,
        }),
      });
    } catch (err) {
      window.clearInterval(watchdog);
      opts?.signal?.removeEventListener("abort", forwardUserAbort);
      if (stalled) {
        throw new ApiError(`Stream stalled with no events for ${STREAM_IDLE_TIMEOUT_MS / 1000}s. Please resend.`, 0, {
          code: "NET0006",
          params: { url },
        });
      }
      if (err instanceof DOMException && err.name === "AbortError") throw err;
      throw new ApiError(`Cannot reach the backend (stream ${url}). Confirm the backend is running`, 0, {
        code: "NET0000",
        params: { url },
      });
    }
    // The watchdog and the user-abort forwarder must stay live through the SSE
    // read: stopping mid-stream or a stalled connection only surfaces there.
    try {
      if (!res.ok) {
        const error = await parseStructuredErrorResponse(res);
        throw new ApiError(error.message, res.status, error);
      }

      let tokenUsage = 0;
      let promptTokens = 0;
      let completionTokens = 0;
      let cachedTokens = 0;
      let promptEstimated = 0;
      let turnId = "";
      let prefixFingerprint = "";
      let messageCount = 0;
      let usage: PrepUsageStats | null = null;
      await consumeSSE<PrepSSEEvent>(res, (event) => {
      touch();
      if (event.type === "token" && typeof event.content === "string") {
        onToken(event.content);
      } else if (event.type === "compaction") {
        onCompaction?.({
          before: Number(event.before) || 0,
          after: Number(event.after) || 0,
          summarized: event.summarized === true,
          prompt_tokens: Number(event.prompt_tokens) || 0,
          completion_tokens: Number(event.completion_tokens) || 0,
          latency_ms: Number(event.latency_ms) || 0,
        });
      } else if (event.type === "thinking" && typeof event.content === "string") {
        onThinking?.(event.content);
      } else if (event.type === "status" && typeof event.text === "string") {
        onStatus?.(event.text);
      } else if (event.type === "tool_step" && typeof event.name === "string") {
        onToolStep?.({
          name: event.name,
          query: String(event.query ?? ""),
          ...(event.args && typeof event.args === "object" ? { args: event.args } : {}),
          result: typeof event.result === "string" ? event.result : "",
        });
      } else if (event.type === "search_results" && Array.isArray(event.groups)) {
        onSearchResults?.(event.groups);
      } else if (
        event.type === "ask_user" &&
        typeof event.question === "string" &&
        Array.isArray(event.options)
      ) {
        onAskUser?.(normalizeAskDialog(event));
      } else if (event.type === "usage") {
        usage = {
          prompt_tokens: Number(event.prompt_tokens) || 0,
          completion_tokens: Number(event.completion_tokens) || 0,
          cached_tokens: Number(event.cached_tokens) || 0,
        };
        onUsage?.(usage);
      } else if (event.type === "done") {
        tokenUsage = Number(event.token_usage) || 0;
        // Session-level provider totals (drift self-healing for usage merge).
        promptTokens = Number(event.prompt_tokens) || 0;
        completionTokens = Number(event.completion_tokens) || 0;
        cachedTokens = Number(event.cached_tokens) || 0;
        // Mechanical estimate of the turn's model input; display fallback only.
        promptEstimated = Number(event.prompt_tokens_estimated) || 0;
        // Turn correlation id (persisted on the assistant message) and the
        // stable-prefix fingerprint for cache-hit measurement.
        turnId = typeof event.turn_id === "string" ? event.turn_id : "";
        prefixFingerprint = typeof event.prefix_fingerprint === "string" ? event.prefix_fingerprint : "";
        // Backend-truth length: tool/trim rounds make client +2 reservations drift.
        messageCount = Number(event.message_count) || 0;
      } else if (event.type === "error") {
        // Backend error-event message is data — pass through; localize only when missing.
        // NOTE: res.status is 200 here by construction (headers preceded the
        // failure); it is threading, not the failure code.
        throw new ApiError(event.message || getTranslator("common")("stream.failed"), res.status);
      }
    }, touch);
      return { token_usage: tokenUsage, prompt_tokens: promptTokens, completion_tokens: completionTokens, cached_tokens: cachedTokens, prompt_tokens_estimated: promptEstimated, turn_id: turnId, prefix_fingerprint: prefixFingerprint, message_count: messageCount, usage };
    } catch (err) {
      // A watchdog abort mid-stream rejects the reader with AbortError; convert
      // it so the caller does not mistake the stall for a user stop.
      if (stalled) {
        throw new ApiError(`Stream stalled with no events for ${STREAM_IDLE_TIMEOUT_MS / 1000}s. Please resend.`, 0, {
          code: "NET0006",
          params: { url },
        });
      }
      throw err;
    } finally {
      window.clearInterval(watchdog);
      opts?.signal?.removeEventListener("abort", forwardUserAbort);
    }
  },
  forkSession: (sessionId: number, upTo: number) =>
    request<PrepSessionCreateResponse>(`/v1/prep/sessions/${sessionId}/fork`, {
      method: "POST",
      body: JSON.stringify({ up_to: upTo }),
    }),
  reissueSession: (sessionId: number) =>
    request<PrepSessionCreateResponse>(`/v1/prep/sessions/${sessionId}/reissue`, {
      method: "POST",
    }),
  truncateMessages: (sessionId: number, fromIndex: number, expectedMessageCount?: number) =>
    request<{ message_count: number }>(`/v1/prep/sessions/${sessionId}/messages/truncate`, {
      method: "POST",
      body: JSON.stringify({
        from_index: fromIndex,
        ...(typeof expectedMessageCount === "number" ? { expected_message_count: expectedMessageCount } : {}),
      }),
    }),
  deleteSession: (sessionId: number) =>
    request<{ deleted: number }>(`/v1/prep/sessions/${sessionId}`, { method: "DELETE" }),
  archiveSession: (sessionId: number, archived: boolean) =>
    request<{ id: number; status: string }>(`/v1/prep/sessions/${sessionId}/archive`, {
      method: "PATCH",
      body: JSON.stringify({ archived }),
    }),
  linkSession: (sessionId: number, linkedId: number | null) =>
    request<{ id: number; linked_session_id: number | null }>(
      `/v1/prep/sessions/${sessionId}/link`,
      { method: "PUT", body: JSON.stringify({ linked_session_id: linkedId }) },
    ),
  purgeEmptySessions: () =>
    request<{ deleted: number }>("/v1/prep/sessions/purge-empty", { method: "POST" }),
  purgeAllSessions: () =>
    request<{ deleted: number }>("/v1/prep/sessions/purge-all", {
      method: "POST",
      body: JSON.stringify({ confirm: true }),
    }),
};

/** Short alias for the prep HTTP client (same object, same behavior). */
export const prepHttp = prepCoachHttp;
