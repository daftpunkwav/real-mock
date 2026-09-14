"use client";

/**
 * @file usePrepChatSession.ts
 * @description Prep session lifecycle: restore/switch/create, local message
 * state seeding, estimate fallback, and provider usage totals. Generation
 * streams run detached per session; switching never blocks on them.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { prepCoachHttp as api } from "@/lib/api/clients";
import { ApiError, resolveBackendUrl } from "@/lib/api/base";
import { getTranslator } from "@/i18n/resolve";
import type { PrepHistoryMessage, PrepSessionSummary } from "@/lib/api/contract";
import type { AskUserDialog, PrepUsageStats } from "@/types";
import type { PrepChatMessage } from "../types";
import { mapHistoryMessages } from "../history";
import { hasActiveStream } from "../streamRegistry";

const RESTORE_KEY = "realmock_prep_session_id";
/** Single retry delay for transport-level history failures. */
const HISTORY_RETRY_MS = 800;
/** Backend liveness probe timeout. */
const HEALTH_PROBE_MS = 5000;

/** True only for transport-level failures (backend unreachable), not HTTP errors. */
function isUnreachable(error: unknown): boolean {
  return error instanceof ApiError && error.code === "NET0000";
}

/** Backend liveness probe to disambiguate outage from transient blip. */
async function isBackendReachable(): Promise<boolean> {
  try {
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), HEALTH_PROBE_MS);
    try {
      const res = await fetch(resolveBackendUrl("/health"), { signal: controller.signal });
      return res.ok;
    } finally {
      window.clearTimeout(timer);
    }
  } catch {
    return false;
  }
}

/** History load with one retry on transport failure, then a probed diagnosis. */
async function loadHistory(id: number): Promise<PrepHistoryMessage[]> {
  try {
    return await api.prepMessages(id);
  } catch (error) {
    // Capability-cookie loss (A0401) on an otherwise listed session: reissue
    // once (owner-level recovery) and retry once; anything else follows the
    // transport-failure path below. Single retry only — never a loop.
    if (error instanceof ApiError && error.code === "A0401") {
      await api.reissueSession(id);
      return await api.prepMessages(id);
    }
    if (!isUnreachable(error)) throw error;
    await new Promise((resolve) => setTimeout(resolve, HISTORY_RETRY_MS));
    try {
      return await api.prepMessages(id);
    } catch (retryError) {
      if (!isUnreachable(retryError)) throw retryError;
      const t = getTranslator("prep");
      throw new Error((await isBackendReachable()) ? t("sessions.backendUnstable") : t("sessions.backendDown"));
    }
  }
}

/** Build usage stats; null when the summary carries none. */
function usageFromSummary(s: PrepSessionSummary | undefined): PrepUsageStats | null {
  if (!s || !(s.prompt_tokens || s.completion_tokens || s.cached_tokens)) return null;
  return {
    prompt_tokens: s.prompt_tokens ?? 0,
    completion_tokens: s.completion_tokens ?? 0,
    cached_tokens: s.cached_tokens ?? 0,
  };
}

interface UsePrepChatSessionOptions {
  setMessages: React.Dispatch<React.SetStateAction<PrepChatMessage[]>>;
  setAskDialog: React.Dispatch<React.SetStateAction<AskUserDialog | null>>;
  nextMsgId: (prefix: string) => string;
  sessions: PrepSessionSummary[];
  resumeId: number | null;
  refreshSessions: () => void;
  /** Max-merge a session's backend message count (never clobbers in-flight reservations). */
  syncBackendCount: (sid: number, n: number) => void;
  /** Absolute set of a session's backend message count (server truth). */
  setBackendCount: (sid: number, n: number) => void;
}

export function usePrepChatSession({
  setMessages,
  setAskDialog,
  nextMsgId,
  sessions,
  resumeId,
  refreshSessions,
  syncBackendCount,
  setBackendCount,
}: UsePrepChatSessionOptions) {
  /**
   * Seed a session's tracked backend length from a fresh server list.
   *
   * The absolute set is required for compaction/truncate heals: max-merge
   * can never follow a server-side history shrink, which permanently
   * inflates the optimistic-concurrency guard (A3003 loop). While a stream
   * is live on that session, reserved indices may sit above server truth,
   * so the max-merge is kept there.
   */
  const seedBackendCount = useCallback(
    (sid: number, n: number) => {
      if (hasActiveStream(sid)) {
        syncBackendCount(sid, n);
      } else {
        setBackendCount(sid, n);
      }
    },
    [syncBackendCount, setBackendCount],
  );
  const [prepSessionId, setPrepSessionId] = useState<number | null>(null);
  const [restoring, setRestoring] = useState(false);
  const [starting, setStarting] = useState(false);
  const [prepError, setPrepError] = useState("");
  const [switchError, setSwitchError] = useState("");
  const [switchFailedId, setSwitchFailedId] = useState<number | null>(null);
  const [tokenUsage, setTokenUsage] = useState(0);
  const [usage, setUsage] = useState<PrepUsageStats | null>(null);
  /** Backend-measured context buckets by stable key (null until first fetch). */
  const [contextBuckets, setContextBuckets] = useState<Record<string, number> | null>(null);
  const [contextTotal, setContextTotal] = useState(0);
  /** Latest turn's mechanical input estimate (display fallback only). */
  const [estimatedPrompt, setEstimatedPrompt] = useState(0);

  /** Guard against overlapping session restores. */
  const restoringRef = useRef(false);
  /** Guard async restores after unmount. */
  const aliveRef = useRef(true);
  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  const resetContext = useCallback(() => {
    setContextBuckets(null);
    setContextTotal(0);
    setEstimatedPrompt(0);
  }, []);

  /** Fetch the backend-measured context breakdown for a session. */
  const refreshContext = useCallback(async (id: number) => {
    try {
      const breakdown = await api.contextBreakdown(id);
      if (!aliveRef.current) return;
      const buckets: Record<string, number> = {};
      for (const b of breakdown.buckets ?? []) {
        if (b && typeof b.key === "string") buckets[b.key] = Number(b.tokens) || 0;
      }
      setContextBuckets(buckets);
      setContextTotal(Number(breakdown.total_estimate) || 0);
    } catch {
      // Keep the previous (or local-estimate fallback) on failure.
    }
  }, []);

  useEffect(() => {
    const saved = Number(window.localStorage.getItem(RESTORE_KEY) || 0);
    if (!saved) return;
    restoringRef.current = true;
    setRestoring(true);
    loadHistory(saved)
      .then((list) => {
        if (!aliveRef.current) return;
        const restored = mapHistoryMessages(list, nextMsgId);
        if (restored.length === 0) throw new Error("empty session");
        setPrepSessionId(saved);
        setMessages(restored);
        seedBackendCount(saved, Array.isArray(list) ? list.length : 0);
        resetContext();
        void refreshContext(saved);
        api
          .listPrepSessions()
          .then((ss) => {
            if (!aliveRef.current) return;
            const hit = (Array.isArray(ss) ? ss : []).find((s) => s.id === saved);
            if (hit) {
              setTokenUsage(hit.token_usage || 0);
              setUsage(usageFromSummary(hit));
            }
          })
          .catch(() => {});
      })
      .catch(() => {
        if (aliveRef.current) window.localStorage.removeItem(RESTORE_KEY);
      })
      .finally(() => {
        if (aliveRef.current) {
          restoringRef.current = false;
          setRestoring(false);
        }
      });
  }, [nextMsgId, setMessages, seedBackendCount, resetContext, refreshContext]);

  /** Reload the current session's history in place (post-compact refresh). */
  const reloadMessages = useCallback(
    async (id: number) => {
      try {
        const list = await loadHistory(id);
        if (!aliveRef.current) return;
        setMessages(mapHistoryMessages(list, nextMsgId));
        seedBackendCount(id, Array.isArray(list) ? list.length : 0);
        resetContext();
        void refreshContext(id);
      } catch {
        // Keep the stale view; the notice already explains the failure.
      }
    },
    [nextMsgId, setMessages, seedBackendCount, resetContext, refreshContext],
  );

  const switchSession = useCallback(    async (id: number) => {
      // Never blocked by generation: background streams keep running detached.
      if (id === prepSessionId || restoringRef.current) return;
      restoringRef.current = true;
      setRestoring(true);
      try {
        const list = await loadHistory(id);
        if (!aliveRef.current) return;
        const restored = mapHistoryMessages(list, nextMsgId);
        if (restored.length === 0) {
          // Keep the current session when the target restores empty.
          return;
        }
        setPrepSessionId(id);
        setMessages(restored);
        seedBackendCount(id, Array.isArray(list) ? list.length : 0);
        setAskDialog(null);
        setTokenUsage(sessions.find((s) => s.id === id)?.token_usage ?? 0);
        setUsage(usageFromSummary(sessions.find((s) => s.id === id)));
        resetContext();
        void refreshContext(id);
        setSwitchError("");
        setSwitchFailedId(null);
        window.localStorage.setItem(RESTORE_KEY, String(id));
      } catch (e) {
        // Drop the stale saved session when nothing is open.
        if (!prepSessionId && aliveRef.current) {
          window.localStorage.removeItem(RESTORE_KEY);
        }
        if (aliveRef.current) {
          const t = getTranslator("prep");
          setSwitchError(
            e instanceof Error
              ? t("sessions.switchFailed", { reason: e.message })
              : t("sessions.switchFailedFallback"),
          );
          // Keep the failed id so the UI can offer orphan cleanup (delete now
          // works without the capability token).
          setSwitchFailedId(id);
        }
      } finally {
        restoringRef.current = false;
        setRestoring(false);
      }
    },
    [prepSessionId, sessions, nextMsgId, setMessages, setAskDialog, seedBackendCount, resetContext, refreshContext],
  );

  const startPrep = useCallback(async () => {
    const t = getTranslator("prep");
    setStarting(true);
    setPrepError("");
    try {
      const { id } = await api.createPrepSession({
        resume_id: resumeId ?? undefined,
      });
      setPrepSessionId(id);
      window.localStorage.setItem(RESTORE_KEY, String(id));
      setTokenUsage(0);
      setUsage(null);
      resetContext();
      syncBackendCount(id, 0);
      setMessages([
        {
          id: nextMsgId("a"),
          role: "assistant",
          content: t("sessions.welcome"),
          // Welcome banner is local-only: never persisted, never in context.
          localOnly: true,
        },
      ]);
      refreshSessions();
      return id;
    } catch (e) {
      setPrepError(e instanceof Error ? e.message : t("sessions.createFailed"));
      return null;
    } finally {
      setStarting(false);
    }
  }, [nextMsgId, resumeId, refreshSessions, setMessages, syncBackendCount, resetContext]);

  const handleNewSession = async () => {
    if (starting || restoringRef.current) return;
    setAskDialog(null);
    await startPrep();
  };

  const mergeUsage = useCallback((u: PrepUsageStats) => {
    // Backend `usage` events carry per-turn DELTAS: add them into the session
    // totals. Session switches reseed from the summary columns instead.
    setUsage((prev) => ({
      prompt_tokens: (prev?.prompt_tokens ?? 0) + u.prompt_tokens,
      completion_tokens: (prev?.completion_tokens ?? 0) + u.completion_tokens,
      cached_tokens: (prev?.cached_tokens ?? 0) + u.cached_tokens,
    }));
  }, []);

  const syncUsage = useCallback((u: PrepUsageStats) => {
    // Server-truth overwrite from the stream `done` envelope: heals drift from
    // missed deltas or background turns finalized while away.
    setUsage({
      prompt_tokens: u.prompt_tokens,
      completion_tokens: u.completion_tokens,
      cached_tokens: u.cached_tokens,
    });
  }, []);

  return {
    prepSessionId,
    restoring,
    starting,
    prepError,
    switchError,
    switchFailedId,
    clearSwitchError: () => {
      setSwitchError("");
      setSwitchFailedId(null);
    },
    tokenUsage,
    setTokenUsage,
    usage,
    mergeUsage,
    syncUsage,
    contextBuckets,
    contextTotal,
    estimatedPrompt,
    setEstimatedPrompt,
    refreshContext,
    switchSession,
    reloadMessages,
    startPrep,
    handleNewSession,
  };
}

