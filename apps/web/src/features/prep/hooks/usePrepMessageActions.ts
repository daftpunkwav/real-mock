"use client";

/**
 * @file usePrepMessageActions.ts
 * @description Per-message actions: export markdown, fork session, regenerate
 * answer, retract user message, and rate-to-memory. Owns the rating dialog state.
 */

import { useCallback, useRef, useState } from "react";
import { toast } from "@/components/Toast";
import { prepCoachHttp as api } from "@/lib/api/clients";
import { prepMemoryHttp } from "@/lib/api/prepMemoryHttp";
import { ApiError, formatApiError } from "@/lib/api/base";
import { getTranslator } from "@/i18n/resolve";
import type { PrepChatMessage } from "../types";
import { downloadTextFile } from "@/lib/download";
import type { RateSubmit } from "../components/RateModal";

import type { PrepSendSnapshot } from "./usePrepSend";

export function usePrepMessageActions(opts: {
  prepSessionId: number | null;
  messages: PrepChatMessage[];
  setMessages: React.Dispatch<React.SetStateAction<PrepChatMessage[]>>;
  /** Abort the viewed session's live stream, if any. */
  stopStream: () => void;
  sendMessage: (
    text: string,
    sessionId?: number,
    skipUserMessage?: boolean,
    sendOpts?: { dropLastAssistant?: boolean; reservedUserIndex?: number; snapshot?: PrepSendSnapshot; contextSessionIds?: number[] },
  ) => Promise<boolean>;
  switchSession: (id: number) => Promise<void>;
  setBackendCount: (sid: number, n: number) => void;
  /** Tracked backend length (optimistic-concurrency guard source). */
  backendCount?: (sid: number) => number | undefined;
  refreshSessions: () => void;
}) {
  const {
    prepSessionId,
    messages,
    setMessages,
    stopStream,
    sendMessage,
    switchSession,
    setBackendCount,
    backendCount,
    refreshSessions,
  } = opts;
  const [rateTarget, setRateTarget] = useState<PrepChatMessage | null>(null);
  const [rateBusy, setRateBusy] = useState(false);
  // Latest-ref mirror: stable callbacks read current messages without taking
  // them as dependencies (otherwise every token flush would rebind every
  // handler and defeat the memoized chat bubbles).
  const messagesRef = useRef(messages);
  messagesRef.current = messages;
  // sendMessage/stopStream rebind on every render (usePrepSend builds them as
  // plain closures), so listing them as deps would rebind regenerate/retract
  // per token flush and defeat the memoized chat bubbles.
  const sendMessageRef = useRef(sendMessage);
  sendMessageRef.current = sendMessage;
  const stopStreamRef = useRef(stopStream);
  stopStreamRef.current = stopStream;

  /** Nearest user message before the given message id (the turn's input). */
  const pairedUserContent = useCallback((id: string): string => {
    const list = messagesRef.current;
    const idx = list.findIndex((m) => m.id === id);
    for (let i = (idx < 0 ? list.length : idx) - 1; i >= 0; i -= 1) {
      if (list[i]?.role === "user") return list[i]?.content ?? "";
    }
    return "";
  }, []);

  const toastFailure = useCallback(
    (
      key: "actions.forkFailed" | "actions.retractFailed" | "actions.rateFailed" | "actions.regenerateFailed",
      err: unknown,
    ) => {
      const t = getTranslator("prep");
      toast.error(err instanceof Error ? formatApiError(err) : t(key));
    },
    [],
  );

  /**
   * Wait for a stopped stream's server-side persist to land: poll history
   * until two consecutive reads agree (or the budget runs out), instead of a
   * fixed grace delay that either wastes time or loses to a slow persist.
   */
  const waitForStoppedPersist = useCallback(
    async (sid: number) => {
      const deadline = Date.now() + 2500;
      let prev = -1;
      while (Date.now() < deadline) {
        try {
          const list = await api.prepMessages(sid);
          const n = Array.isArray(list) ? list.length : 0;
          if (n === prev) {
            setBackendCount(sid, n);
            return;
          }
          prev = n;
        } catch {
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 250));
      }
    },
    [setBackendCount],
  );

  const handleExport = useCallback(
    (msg: PrepChatMessage) => {
      downloadTextFile(`prep-${prepSessionId ?? "chat"}-${msg.id}.md`, msg.content);
    },
    [prepSessionId],
  );

  const handleFork = useCallback(
    async (msg: PrepChatMessage) => {
      const t = getTranslator("prep");
      if (!prepSessionId || msg.backendIndex === undefined) return;
      try {
        // Non-destructive: the fork copies persisted history (an in-flight
        // partial turn is excluded) and the live stream keeps running.
        const { id } = await api.forkSession(prepSessionId, msg.backendIndex);
        refreshSessions();
        await switchSession(id);
      } catch (err) {
        toastFailure("actions.forkFailed", err instanceof Error ? err : new Error(t("actions.forkFailed")));
      }
    },
    [prepSessionId, refreshSessions, switchSession, toastFailure],
  );

  /**
   * Fork from a compaction record: rebuild a new session from the
   * pre-compaction originals (backup session) through the recorded fork
   * point, or through the whole backup to review it verbatim.
   */
  const handleCompactionFork = useCallback(
    async (backupSessionId: number, upTo: number) => {
      try {
        const { id } = await api.forkSession(backupSessionId, upTo);
        refreshSessions();
        await switchSession(id);
      } catch (err) {
        toastFailure("actions.forkFailed", err);
      }
    },
    [refreshSessions, switchSession, toastFailure],
  );

  /** Open the archived pre-compaction backup session for review. */
  const handleCompactionOpen = useCallback(
    async (backupSessionId: number) => {
      try {
        refreshSessions();
        await switchSession(backupSessionId);
      } catch (err) {
        toastFailure("actions.forkFailed", err);
      }
    },
    [refreshSessions, switchSession, toastFailure],
  );

  const handleRegenerate = useCallback(
    async (msg: PrepChatMessage) => {
      const t = getTranslator("prep");
      // drop_last_assistant pops the backend's trailing reply, so only the
      // latest assistant message may be regenerated; older turns would orphan.
      const lastAssistant = [...messagesRef.current].reverse().find((m) => m.role === "assistant");
      if (!lastAssistant || lastAssistant.id !== msg.id) {
        toast.error(t("actions.regenerateLatestOnly"));
        return;
      }
      const input = pairedUserContent(msg.id);
      if (!input) {
        toast.error(t("actions.regenerateFailed"));
        return;
      }
      // Stop the live stream first so its stopped partial lands before the rerun.
      stopStreamRef.current();
      if (prepSessionId != null) await waitForStoppedPersist(prepSessionId);
      setMessages((m) => m.filter((x) => x.id !== msg.id));
      void sendMessageRef.current(input, undefined, true, { dropLastAssistant: true });
    },
    [pairedUserContent, prepSessionId, setMessages, waitForStoppedPersist],
  );

  const handleRetract = useCallback(
    async (msg: PrepChatMessage) => {
      if (!prepSessionId || msg.backendIndex === undefined) return;
      const cut = msg.backendIndex;
      // Retracting under a live stream would resurrect the stopped partial
      // after the cut: stop first, then truncate once it has landed. A stale
      // count guard (a background turn landed mid-retract) resyncs once from
      // the backend and retries once, then reports.
      for (let retried = false; ; retried = true) {
        try {
          stopStreamRef.current();
          await waitForStoppedPersist(prepSessionId);
          await api.truncateMessages(prepSessionId, cut, backendCount?.(prepSessionId));
          const idx = messagesRef.current.findIndex((m) => m.id === msg.id);
          setMessages((m) => (idx < 0 ? m : m.slice(0, idx)));
          setBackendCount(prepSessionId, cut);
          refreshSessions();
          return;
        } catch (err) {
          if (retried || !(err instanceof ApiError) || err.code !== "A3003") {
            toastFailure("actions.retractFailed", err);
            return;
          }
          try {
            const list = await api.prepMessages(prepSessionId);
            setBackendCount(prepSessionId, Array.isArray(list) ? list.length : 0);
          } catch {
            // Resync failure surfaces via the retry below.
          }
        }
      }
    },
    [
      prepSessionId,
      waitForStoppedPersist,
      backendCount,
      setMessages,
      setBackendCount,
      refreshSessions,
      toastFailure,
    ],
  );

  const openRate = useCallback((msg: PrepChatMessage) => {
    setRateTarget(msg);
  }, []);

  const closeRate = useCallback(() => {
    if (!rateBusy) setRateTarget(null);
  }, [rateBusy]);

  const submitRate = useCallback(
    async (data: RateSubmit) => {
      const t = getTranslator("prep");
      if (!rateTarget) return;
      setRateBusy(true);
      try {
        await prepMemoryHttp.createFromRating({
          session_id: prepSessionId ?? undefined,
          user_input: pairedUserContent(rateTarget.id).slice(0, 8000),
          agent_output: rateTarget.content.slice(0, 8000),
          score: data.score,
          reasons: data.reasons,
          comment: data.comment,
          tags: data.tags,
          origin: "user_rating",
        });
        toast.success(t("actions.rateDone"));
        setRateTarget(null);
      } catch (err) {
        toastFailure("actions.rateFailed", err);
      } finally {
        setRateBusy(false);
      }
    },
    [pairedUserContent, prepSessionId, rateTarget, toastFailure],
  );

  return {
    handleExport,
    handleFork,
    handleRegenerate,
    handleRetract,
    handleCompactionFork,
    handleCompactionOpen,
    openRate,
    closeRate,
    submitRate,
    rateTarget,
    rateBusy,
  };
}
