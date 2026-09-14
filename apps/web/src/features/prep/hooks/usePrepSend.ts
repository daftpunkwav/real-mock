"use client";

/**
 * @file usePrepSend.ts
 * @description Prep send pipeline: per-session queueing, streaming handlers,
 * abort/stop, usage merge, and backend-index bookkeeping for fork/retract actions.
 *
 * Generations are non-blocking and survive session switches and in-app
 * navigation: each stream is registered per session, view updates only apply
 * while that session is visible, and the server persists every finished turn.
 *
 * Model/effort snapshot: every send resolves the model profile, reasoning
 * effort, and locale at enqueue time. Queued turns replay their own snapshot,
 * so switching the global selectors mid-stream only affects later sends —
 * the in-flight turn is never disturbed.
 *
 * Usage accounting: the backend `usage` event carries the turn DELTA (added
 * via mergeUsage); the terminal `done` envelope carries session TOTALS
 * (applied via syncUsage as drift self-healing).
 */

import { useEffect, useRef, type MutableRefObject } from "react";
import { prepCoachHttp as api } from "@/lib/api/clients";
import { getTranslator } from "@/i18n/resolve";
import { readCompactThreshold, resolveCompactParams, toCompactThresholdParam } from "@/lib/compactThreshold";
import type { AskUserDialog, ModelProfile, PrepUsageStats, ReasoningEffort } from "@/types";
import { resolveSelectedModel } from "../modelChoice";
import { appendTraceThinking, appendTraceTool } from "../history";
import { abortStream, completeStream, hasActiveStream, registerStream } from "../streamRegistry";
import type { PrepChatMessage, PrepStreamHandlers } from "../types";

/** Model/locale snapshot bound to one send (replayed by queued turns). */
export interface PrepSendSnapshot {
  modelProfileId: number | null;
  reasoningEffort: ReasoningEffort | null;
  uiLocale: string;
  /** Per-turn "#" referenced session ids (transient backend injection). */
  contextSessionIds: number[];
}

interface QueuedSend {
  text: string;
  userBackendIndex?: number;
  snapshot: PrepSendSnapshot;
}

export function usePrepSend(opts: {
  prepSessionId: number | null;
  restoring: boolean;
  input: string;
  setInput: (v: string) => void;
  setMessages: React.Dispatch<React.SetStateAction<PrepChatMessage[]>>;
  setTokenUsage: (v: number) => void;
  setAskDialog: React.Dispatch<React.SetStateAction<AskUserDialog | null>>;
  setBusySid: React.Dispatch<React.SetStateAction<number | null>>;
  nextMsgId: (prefix: string) => string;
  patchMessage: (id: string, patch: Partial<PrepChatMessage>) => void;
  queueToken: (id: string, text: string) => void;
  flushPendingToken: () => void;
  stickToBottom: () => void;
  /** Add one turn DELTA to the session totals (backend `usage` event). */
  mergeUsage: (u: PrepUsageStats) => void;
  /** Overwrite session totals with server truth (stream `done` envelope). */
  syncUsage: (u: PrepUsageStats) => void;
  /** Latest turn's mechanical input estimate (display fallback only). */
  setEstimatedPrompt: (v: number) => void;
  /** Refetch the backend-measured context breakdown for a session. */
  refreshContext: (id: number) => Promise<void>;
  onAskUser?: (dialog: AskUserDialog) => void;
  startPrep: () => Promise<number | null>;
  chatModels: ModelProfile[];
  selectedModelId: number | null;
  defaultChatProfile: ModelProfile | null;
  effort: ReasoningEffort;
  uiLocale: string;
  refreshSessions: () => void;
  /** Currently viewed session id (fresh on every render). */
  viewingRef: MutableRefObject<number | null>;
  /** Reserve n backend message indices for a session; returns the first index. */
  takeBackendIndex: (sid: number, n: number) => number;
  /** Max-merge the backend message count of a session (restore/switch/resync). */
  syncBackendCount: (sid: number, n: number) => void;
  /** True while a manual compaction is in flight for the session (send backstop). */
  isCompacting?: (sid: number) => boolean;
}) {
  const queuesRef = useRef(new Map<number, QueuedSend[]>());
  /** Guard delayed sends after unmount (streams themselves keep running). */
  const aliveRef = useRef(true);
  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);
  const {
    prepSessionId,
    restoring,
    input,
    setInput,
    setMessages,
    setTokenUsage,
    setAskDialog,
    setBusySid,
    nextMsgId,
    patchMessage,
    queueToken,
    flushPendingToken,
    stickToBottom,
    mergeUsage,
    syncUsage,
    setEstimatedPrompt,
    refreshContext,
    onAskUser,
    startPrep,
    chatModels,
    selectedModelId,
    defaultChatProfile,
    effort,
    uiLocale,
    refreshSessions,
    viewingRef,
    takeBackendIndex,
    syncBackendCount,
    isCompacting,
  } = opts;

  const isViewing = (sid: number) => viewingRef.current === sid;

  const resolveSnapshot = (contextSessionIds?: number[]): PrepSendSnapshot => {
    const selectedModel = resolveSelectedModel(chatModels, selectedModelId, defaultChatProfile);
    return {
      modelProfileId: selectedModel?.id ?? null,
      reasoningEffort: selectedModel?.capabilities.reasoning ? effort : null,
      uiLocale,
      contextSessionIds: contextSessionIds ?? [],
    };
  };

  const enqueue = (sid: number, text: string, snapshot: PrepSendSnapshot, userBackendIndex?: number) => {
    const queue = queuesRef.current.get(sid) ?? [];
    queue.push({ text, userBackendIndex, snapshot });
    queuesRef.current.set(sid, queue);
  };

  const sendMessage = async (
    text: string,
    sessionId?: number,
    skipUserMessage?: boolean,
    sendOpts?: {
      dropLastAssistant?: boolean;
      reservedUserIndex?: number;
      assumeViewing?: boolean;
      /** Replay snapshot for dequeued turns; fresh sends resolve one now. */
      snapshot?: PrepSendSnapshot;
      /** "#" referenced session ids for this turn (folded into the snapshot). */
      contextSessionIds?: number[];
    },
  ) => {
    const sid = sessionId ?? prepSessionId;
    if (!text.trim() || !sid) return;
    // Manual compaction rewrites persisted history mid-flight: a turn sent
    // during it would finalize on top of stale agent state and drop the new
    // summary. The composer is disabled while compacting; this guard is the
    // backstop for every other send entry point.
    if (isCompacting?.(sid)) return;
    const userMsg = text.trim();
    const dropLast = sendOpts?.dropLastAssistant === true;
    const snapshot = sendOpts?.snapshot ?? resolveSnapshot(sendOpts?.contextSessionIds);
    // Freshly created sessions have a stale viewing ref until the next render.
    const viewing = sendOpts?.assumeViewing === true || isViewing(sid);

    if (hasActiveStream(sid)) {
      // Same session is generating: queue behind it (reserve indices now so the
      // bubble carries its backend index even when composed while streaming).
      const queuedIndex = sendOpts?.reservedUserIndex ?? takeBackendIndex(sid, 2);
      if (viewing && !skipUserMessage) {
        setMessages((m) => [
          ...m,
          { id: nextMsgId("u"), role: "user", content: userMsg, backendIndex: queuedIndex },
        ]);
      }
      enqueue(sid, userMsg, snapshot, queuedIndex);
      setInput("");
      return;
    }
    // Regenerate drops the stale assistant reply locally; the backend drops it too.
    if (viewing && dropLast) {
      setMessages((m) => (m.length > 0 && m[m.length - 1]?.role === "assistant" ? m.slice(0, -1) : m));
    }
    // Reserve backend indices: user + assistant (net +1 when regenerating).
    // Queued follow-ups reuse the index reserved when they were queued.
    const userBackendIndex = sendOpts?.reservedUserIndex ?? takeBackendIndex(sid, dropLast ? 1 : 2);
    const assistantId = nextMsgId("a");
    if (viewing) {
      if (!skipUserMessage) {
        setMessages((m) => [
          ...m,
          { id: nextMsgId("u"), role: "user", content: userMsg, backendIndex: userBackendIndex },
        ]);
      }
      setMessages((m) => [
        ...m,
        {
          id: assistantId,
          role: "assistant",
          content: "",
          streaming: true,
          trace: [],
          backendIndex: userBackendIndex + 1,
        },
      ]);
      setInput("");
      setBusySid(sid);
      stickToBottom();
    }

    const appendTrace = (updater: (trace: NonNullable<PrepChatMessage["trace"]>) => NonNullable<PrepChatMessage["trace"]>) => {
      setMessages((m) =>
        m.map((msg) =>
          msg.id === assistantId ? { ...msg, trace: updater(msg.trace ?? []) } : msg,
        ),
      );
    };
    const handlers: PrepStreamHandlers = {
      onToken: (token) => queueToken(assistantId, token),
      onThinking: (chunk) => {
        appendTrace((trace) => appendTraceThinking(trace, chunk));
      },
      onSearchResults: (groups) => {
        setMessages((m) =>
          m.map((msg) =>
            msg.id === assistantId
              ? { ...msg, searchGroups: [...(msg.searchGroups ?? []), ...groups] }
              : msg,
          ),
        );
      },
      onStatus: (status) => patchMessage(assistantId, { statusText: status }),
      onToolStep: (step) => {
        appendTrace((trace) => appendTraceTool(trace, step));
      },
      onCompaction: (event) => {
        appendTrace((trace) => [
          ...trace,
          {
            kind: "compaction",
            before: event.before,
            after: event.after,
            summarized: event.summarized,
          },
        ]);
      },
      onAskUser: (dialog) => {
        // Dialogs only interrupt the visible session; background turns finalize
        // server-side and surface on revisit.
        if (!isViewing(sid)) return;
        flushPendingToken();
        patchMessage(assistantId, { statusText: "" });
        setAskDialog(dialog);
        onAskUser?.(dialog);
      },
      onUsage: (u) => {
        if (isViewing(sid)) mergeUsage(u);
      },
    };

    const controller = new AbortController();
    registerStream(sid, controller);
    try {
      const params = resolveCompactParams();
      const result = await api.prepMessageStream(sid, userMsg, handlers, {
        modelProfileId: snapshot.modelProfileId,
        reasoningEffort: snapshot.reasoningEffort,
        dropLastAssistant: dropLast,
        uiLocale: snapshot.uiLocale,
        contextSessionIds: snapshot.contextSessionIds,
        // Auto-compact trigger follows the prep settings choice (read fresh
        // per turn so a settings change applies without reload).
        compactThreshold: toCompactThresholdParam(readCompactThreshold()),
        compactIntensity: params.intensity,
        compactDirective: params.directive || undefined,
        compactRetain: params.retain,
        signal: controller.signal,
      });
      flushPendingToken();
      if (isViewing(sid)) {
        setTokenUsage(result.token_usage);
        // Backend-truth length resync (tool/trim rounds drift reservations).
        if (result.message_count > 0) syncBackendCount(sid, result.message_count);
        // Server-truth resync: heals drift from missed deltas or background turns.
        if (result.prompt_tokens > 0 || result.completion_tokens > 0) {
          syncUsage({
            prompt_tokens: result.prompt_tokens,
            completion_tokens: result.completion_tokens,
            cached_tokens: result.cached_tokens,
          });
        }
        if (result.prompt_tokens_estimated > 0) {
          setEstimatedPrompt(result.prompt_tokens_estimated);
        }
        patchMessage(assistantId, { streaming: false, statusText: "" });
      }
    } catch (e) {
      flushPendingToken();
      if (e instanceof DOMException && e.name === "AbortError") {
        // Stop button: the backend persists the partial turn as stopped.
        if (isViewing(sid)) {
          patchMessage(assistantId, { streaming: false, statusText: "", stopped: true });
        }
        // The stopped persist lands just after the abort: delayed resync so a
        // following /compact sees the true length instead of a stale count.
        setTimeout(() => {
          if (!aliveRef.current) return;
          api
            .prepMessages(sid)
            .then((list) => {
              if (aliveRef.current) syncBackendCount(sid, Array.isArray(list) ? list.length : 0);
            })
            .catch(() => {});
        }, 800);
      } else if (isViewing(sid)) {
        const t = getTranslator("prep");
        const reason = e instanceof Error ? e.message : t("chat.sendFailedFallback");
        setMessages((m) =>
          m.map((msg) =>
            msg.id === assistantId
              ? {
                  ...msg,
                  streaming: false,
                  statusText: "",
                  // Failed turns never reached the backend: exclude from context
                  // estimation while keeping the visible error text.
                  localOnly: true,
                  // Append an interruption notice or fall back to error text.
                  content: msg.content
                    ? `${msg.content}\n\n> ${t("chat.replyInterrupted", { reason })}`
                    : t("chat.replyError", { reason }),
                }
              : msg,
          ),
        );
        // Backend indices may have drifted when the turn never finalized: resync.
        api
          .prepMessages(sid)
          .then((list) => {
            if (aliveRef.current) syncBackendCount(sid, Array.isArray(list) ? list.length : 0);
          })
          .catch(() => {});
      }
    } finally {
      completeStream(sid);
      if (isViewing(sid)) {
        setBusySid((prev) => (prev === sid ? null : prev));
      }
      refreshSessions();
      // Breakdown buckets are global view state: refresh only for the session
      // on screen (background sessions reseed on switch).
      if (isViewing(sid)) void refreshContext(sid);
      const queue = queuesRef.current.get(sid) ?? [];
      const [next, ...rest] = queue;
      queuesRef.current.set(sid, rest);
      if (next) {
        setTimeout(() => {
          if (!aliveRef.current) return;
          void sendMessage(next.text, sid, true, {
            reservedUserIndex: next.userBackendIndex,
            snapshot: next.snapshot,
          });
        }, 50);
      }
    }
  };

  const handleSend = () => {
    void sendMessage(input);
  };

  /**
   * Stop a session's live stream (default: the viewed session) and clear its
   * queued follow-ups. Background sessions are stoppable the same way.
   */
  const handleStop = (sid?: number) => {
    const target = sid ?? viewingRef.current;
    if (!target || !hasActiveStream(target)) return;
    // Cleared queue entries reserved indices that will never materialize:
    // release them synchronously (a server resync here would race finalization).
    const cleared = queuesRef.current.get(target)?.length ?? 0;
    queuesRef.current.set(target, []);
    if (cleared > 0) takeBackendIndex(target, -2 * cleared);
    abortStream(target);
  };

  const handleAskAnswer = (text: string) => {
    setAskDialog(null);
    void sendMessage(text);
  };

  const handleQuickPrompt = async (prompt: string) => {
    if (restoring) return;
    if (!prepSessionId) {
      const id = await startPrep();
      if (!id) return;
      await sendMessage(prompt, id, false, { assumeViewing: true });
      return;
    }
    await sendMessage(prompt);
  };

  return { handleSend, handleStop, handleAskAnswer, handleQuickPrompt, sendMessage };
}
