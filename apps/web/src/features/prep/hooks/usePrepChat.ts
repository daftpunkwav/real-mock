"use client";

/**
 * @file usePrepChat.ts
 * @description Prep chat composition root: wires resources, session state,
 * send pipeline, message actions, and session management into one view-model.
 * Exposes per-session busy state so background generations stay visible and
 * stoppable from the session list.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useLocale } from "@/i18n";
import { getTranslator } from "@/i18n/resolve";
import { formatTokens } from "@/components/ModelControls";
import { prepCoachHttp as api } from "@/lib/api/clients";
import { ApiError, formatApiError } from "@/lib/api/base";
import type { PrepSessionSummary } from "@/lib/api/contract";
import type { AskUserDialog, PrepUsageStats } from "@/types";
import type { PrepChatMessage } from "../types";
import type { RateSubmit } from "../components/RateModal";
import type { SlashName } from "../slashCommands";
import { parseCompactArgs } from "../slashCommands";
import { resolveCompactParams } from "@/lib/compactThreshold";
import { loadArchive, pushArchivedGroup, toArchivedCopy, type ArchivedGroup } from "../compactionArchive";
import type { PendingSessionRef } from "../sessionRefs";
import { activeStreamIds, hasActiveStream, subscribeStreams } from "../streamRegistry";
import { usePrepResources } from "./usePrepResources";
import { usePrepScroll } from "./usePrepScroll";
import { usePrepSend } from "./usePrepSend";
import { useTokenBatch } from "./useTokenBatch";
import { usePrepChatSession } from "./usePrepChatSession";
import { usePrepMessageActions } from "./usePrepMessageActions";
import { usePrepSessionManage } from "./usePrepSessionManage";

interface UsePrepChatOptions {
  /** Optional ask_user listener alongside the ask dialog. */
  onAskUser?: (dialog: AskUserDialog) => void;
}

interface UsePrepChat {
  messages: PrepChatMessage[];
  setMessages: React.Dispatch<React.SetStateAction<PrepChatMessage[]>>;
  input: string;
  setInput: (v: string) => void;
  loading: boolean;
  /** True while a manual compaction is in flight for the viewed session. */
  compacting: boolean;
  /** Sessions with a live generation stream (viewed or background). */
  busySids: number[];
  /** Stop any session's live stream (default: the viewed session). */
  stopSession: (sid?: number) => void;
  starting: boolean;
  restoring: boolean;
  prepError: string;
  switchError: string;
  switchFailedId: number | null;
  clearSwitchError: () => void;
  prepSessionId: number | null;
  resumes: ReturnType<typeof usePrepResources>["resumes"];
  resumeId: number | null;
  setResumeId: (v: number | null) => void;
  resumeLoadError: string;
  sessions: PrepSessionSummary[];
  askDialog: AskUserDialog | null;
  chatModels: ReturnType<typeof usePrepResources>["chatModels"];
  selectedModelId: number | null;
  setSelectedModelId: (v: number | null) => void;
  defaultChatProfile: ReturnType<typeof usePrepResources>["defaultChatProfile"];
  effort: ReturnType<typeof usePrepResources>["effort"];
  setEffort: ReturnType<typeof usePrepResources>["setEffort"];
  tokenUsage: number;
  usage: PrepUsageStats | null;
  contextBuckets: Record<string, number> | null;
  contextTotal: number;
  estimatedPrompt: number;
  showJump: boolean;
  chatScrollRef: React.RefObject<HTMLDivElement | null>;
  contentRef: React.RefObject<HTMLDivElement | null>;
  handleSend: () => void;
  handleStop: () => void;
  /** Sessions referenced via "#" chips, attached to the next main send only. */
  pendingRefs: PendingSessionRef[];
  addRef: (ref: PendingSessionRef) => void;
  removeRef: (id: number) => void;
  handleSlashCommand: (cmd: SlashName, args: string) => void;
  slashClearOpen: boolean;
  confirmSlashClear: () => void;
  cancelSlashClear: () => void;
  handleAskAnswer: (text: string) => void;
  handleQuickPrompt: (prompt: string) => Promise<void>;
  handleNewSession: () => Promise<void>;
  handleScroll: () => void;
  jumpToBottom: () => void;
  switchSession: (id: number) => Promise<void>;
  reloadMessages: (id: number) => Promise<void>;
  /** Tracked backend message-list length (fork/retract/compact guards). */
  backendCount: (sid: number) => number | undefined;
  startPrep: () => Promise<number | null>;
  setAskDialog: React.Dispatch<React.SetStateAction<AskUserDialog | null>>;
  deleteSession: (id: number) => Promise<void>;
  archiveSession: (id: number, archived: boolean) => Promise<void>;
  clearSession: (id: number) => Promise<void>;
  messageActions: {
    onExport: (msg: PrepChatMessage) => void;
    onFork: (msg: PrepChatMessage) => void;
    onRegenerate: (msg: PrepChatMessage) => void;
    onRate: (msg: PrepChatMessage) => void;
    onRetract: (msg: PrepChatMessage) => void;
  };
  compactionActions: {
    onForkFromPoint: (backupSessionId: number, upTo: number) => void;
    onOpenBackup: (backupSessionId: number) => void;
    onReload: () => void;
    onRegenerate: () => void;
  };
  /** Display-only archive groups of folded turns (oldest first). */
  archiveGroups: ArchivedGroup[];
  rateTarget: PrepChatMessage | null;
  rateBusy: boolean;
  closeRate: () => void;
  submitRate: (data: RateSubmit) => Promise<void>;
}

export function usePrepChat({ onAskUser }: UsePrepChatOptions = {}): UsePrepChat {
  const resources = usePrepResources();
  const { locale } = useLocale();
  const [messages, setMessages] = useState<PrepChatMessage[]>([]);
  const [input, setInput] = useState("");
  /** Session with a live stream relevant to the view (composer stop/send toggle). */
  const [busySid, setBusySid] = useState<number | null>(null);
  /** All sessions with a live stream (background visibility badges). */
  const [busySids, setBusySids] = useState<number[]>(() => activeStreamIds());
  useEffect(() => subscribeStreams(setBusySids), []);
  const [askDialog, setAskDialog] = useState<AskUserDialog | null>(null);
  /** Slash-/clear confirmation dialog owned by the page. */
  const [slashClearOpen, setSlashClearOpen] = useState(false);
  /** Display-only archive of folded turns (backend keeps only the summary). */
  const [archiveGroups, setArchiveGroups] = useState<ArchivedGroup[]>([]);
  /** Session with a manual compaction in flight (blocks sends + shows progress). */
  const [compactingSid, setCompactingSid] = useState<number | null>(null);
  /** Ref mirror of compactingSid: stable guard for callbacks without re-binding. */
  const compactingRef = useRef<Set<number>>(new Set());

  const msgSeqRef = useRef(0);
  /** Backend message-list lengths per session, for fork/retract indices. */
  const backendCountsRef = useRef(new Map<number, number>());
  /** Currently viewed session id (fresh on every render, for stream guards). */
  const viewingRef = useRef<number | null>(null);
  const takeBackendIndex = useCallback((sid: number, n: number) => {
    const start = backendCountsRef.current.get(sid) ?? 0;
    backendCountsRef.current.set(sid, start + n);
    return start;
  }, []);
  const setBackendCount = useCallback((sid: number, n: number) => {
    backendCountsRef.current.set(sid, n);
  }, []);
  /** Max-merge: adopt server truth without clobbering in-flight reservations. */
  const syncBackendCount = useCallback((sid: number, n: number) => {
    backendCountsRef.current.set(sid, Math.max(n, backendCountsRef.current.get(sid) ?? 0));
  }, []);
  /** Read the tracked backend length (optimistic-concurrency guard source). */
  const backendCount = useCallback((sid: number) => backendCountsRef.current.get(sid), []);
  const scroll = usePrepScroll(messages.length);
  const { flushPendingToken, queueToken } = useTokenBatch(setMessages);

  const nextMsgId = useCallback((prefix: string) => {
    msgSeqRef.current += 1;
    return `${prefix}-${msgSeqRef.current}`;
  }, []);

  const patchMessage = useCallback((id: string, patch: Partial<PrepChatMessage>) => {
    setMessages((m) => m.map((msg) => (msg.id === id ? { ...msg, ...patch } : msg)));
  }, []);

  const session = usePrepChatSession({
    setMessages,
    setAskDialog,
    nextMsgId,
    sessions: resources.sessions,
    resumeId: resources.resumeId,
    refreshSessions: resources.refreshSessions,
    syncBackendCount,
    setBackendCount,
  });
  viewingRef.current = session.prepSessionId;
  const loading = busySid !== null && busySid === session.prepSessionId;

  // Display archive follows the viewed session (loaded once per switch).
  useEffect(() => {
    const id = session.prepSessionId;
    if (id === null) {
      setArchiveGroups([]);
      return;
    }
    setArchiveGroups(loadArchive(id)?.groups ?? []);
  }, [session.prepSessionId]);

  const { handleStop, handleAskAnswer, handleQuickPrompt, sendMessage } = usePrepSend({
    prepSessionId: session.prepSessionId,
    restoring: session.restoring,
    input,
    setInput,
    setMessages,
    setTokenUsage: session.setTokenUsage,
    setAskDialog,
    setBusySid,
    nextMsgId,
    patchMessage,
    queueToken,
    flushPendingToken,
    stickToBottom: scroll.stickToBottom,
    mergeUsage: session.mergeUsage,
    syncUsage: session.syncUsage,
    setEstimatedPrompt: session.setEstimatedPrompt,
    refreshContext: session.refreshContext,
    onAskUser,
    startPrep: session.startPrep,
    chatModels: resources.chatModels,
    selectedModelId: resources.selectedModelId,
    defaultChatProfile: resources.defaultChatProfile,
    effort: resources.effort,
    uiLocale: locale,
    refreshSessions: resources.refreshSessions,
    viewingRef,
    takeBackendIndex,
    syncBackendCount,
    isCompacting: (sid: number) => compactingRef.current.has(sid),
  });

  const actions = usePrepMessageActions({
    prepSessionId: session.prepSessionId,
    messages,
    setMessages,
    stopStream: handleStop,
    sendMessage,
    switchSession: session.switchSession,
    setBackendCount,
    refreshSessions: resources.refreshSessions,
  });

  const manage = usePrepSessionManage({
    prepSessionId: session.prepSessionId,
    setMessages,
    setAskDialog,
    nextMsgId,
    stopStream: handleStop,
    startPrep: session.startPrep,
    setBackendCount,
    refreshSessions: resources.refreshSessions,
  });

  /** "#" reference chips: attached to the next main send only (transient). */
  const [pendingRefs, setPendingRefs] = useState<PendingSessionRef[]>([]);
  const addRef = useCallback((ref: PendingSessionRef) => {
    setPendingRefs((prev) => (prev.some((p) => p.id === ref.id) ? prev : [...prev, ref]));
  }, []);
  const removeRef = useCallback((id: number) => {
    setPendingRefs((prev) => prev.filter((p) => p.id !== id));
  }, []);

  /** Main send: consumes pending "#" refs into the snapshot, then clears them. */
  const handleSend = useCallback(() => {
    const ids = pendingRefs.map((r) => r.id);
    setPendingRefs([]);
    void sendMessage(input, undefined, false, ids.length > 0 ? { contextSessionIds: ids } : undefined);
  }, [input, pendingRefs, sendMessage]);

  /** Append a local-only notice (never persisted, never in context). */
  const pushNotice = useCallback(
    (text: string) => {
      setMessages((m) => [...m, { id: nextMsgId("n"), role: "assistant", content: text, localOnly: true }]);
    },
    [nextMsgId],
  );

  /**
   * Archive-aware manual compaction shared by /compact and card regenerate:
   * fold the reported range into a display group, reload backend truth
   * (indices shift on rewrite), and bring the newest card into view.
   */
  const runCompactAttempt = useCallback(
    async (sid: number, params: { intensity: "light" | "balanced" | "aggressive"; directive?: string; retain: number; backup?: boolean }) => {
      const t = getTranslator("prep");
      const attempt = async (retried: boolean): Promise<void> => {
        try {
          const result = await api.compactSession(sid, {
            ...params,
            expected_message_count: backendCount(sid) ?? undefined,
          });
          // Archive the folded turns for display (backend keeps only the summary).
          if (
            typeof result.kept_from === "number" &&
            typeof result.backup_session_id === "number"
          ) {
            const folded = messages.filter(
              (m) =>
                !m.localOnly &&
                (m.role === "user" || m.role === "assistant") &&
                m.backendIndex !== undefined &&
                m.backendIndex < (result.kept_from as number),
            );
            if (folded.length > 0) {
              const next = pushArchivedGroup(sid, {
                version: result.summary_version,
                forkPoint: result.fork_point ?? 0,
                backupSessionId: result.backup_session_id,
                staleBackup: false,
                messages: folded.map(toArchivedCopy),
              });
              setArchiveGroups(next.groups);
            }
          }
          const key =
            result.reason === "nothing_to_fold"
              ? "slash.compactDoneUnchanged"
              : result.summarized
                ? "slash.compactDoneSummary"
                : "slash.compactDonePruned";
          pushNotice(
            t(key, {
              before: formatTokens(result.estimate_before),
              after: formatTokens(result.estimate_after),
            }),
          );
          resources.refreshSessions();
          // Reload backend truth so retained-tail indices match the rewrite.
          await session.reloadMessages(sid);
          requestAnimationFrame(() => {
            const cards = document.querySelectorAll("[data-compaction-card]");
            cards[cards.length - 1]?.scrollIntoView({ block: "center" });
          });
        } catch (e) {
          // Stale count guard fired (background/stopped turns moved history):
          // resync once from the backend and retry once, then report.
          if (!retried && e instanceof ApiError && e.code === "A3003") {
            await session.reloadMessages(sid);
            await attempt(true);
            return;
          }
          pushNotice(
            t("slash.compactFailed", {
              reason: e instanceof Error ? formatApiError(e) : String(e),
            }),
          );
        }
      };
      await attempt(false);
    },
    [backendCount, messages, pushNotice, resources, session],
  );

  const runCompact = useCallback(
    async (sid: number, params: { intensity: "light" | "balanced" | "aggressive"; directive?: string; retain: number; backup?: boolean }) => {
      const t = getTranslator("prep");
      // Compact rewrites persisted history: refuse while this session has any
      // live stream — viewed or background (the in-flight turn would overwrite
      // the compaction on finalize) — or while another compaction of the same
      // session is already running.
      if (hasActiveStream(sid)) {
        pushNotice(t("slash.compactBusy"));
        return;
      }
      if (compactingRef.current.has(sid)) return;
      compactingRef.current.add(sid);
      setCompactingSid(sid);
      try {
        await runCompactAttempt(sid, params);
      } finally {
        compactingRef.current.delete(sid);
        setCompactingSid((prev) => (prev === sid ? null : prev));
      }
    },
    [pushNotice, runCompactAttempt],
  );

  const handleSlashCommand = useCallback(
    async (cmd: SlashName, rawArgs: string) => {
      const t = getTranslator("prep");
      setInput("");
      if (cmd === "help") {
        pushNotice(t("slash.helpBody"));
        return;
      }
      const sid = session.prepSessionId;
      if (!sid) {
        pushNotice(t("slash.noSession"));
        return;
      }
      if (cmd === "clear") {
        setSlashClearOpen(true);
        return;
      }
      // Slash args override settings for this run only: an intensity
      // keyword selects the amplitude, the rest is the directive.
      const slashArgs = parseCompactArgs(rawArgs);
      const settings = resolveCompactParams();
      await runCompact(sid, {
        intensity: slashArgs.intensity ?? settings.intensity,
        ...(slashArgs.directive !== undefined
          ? { directive: slashArgs.directive }
          : settings.directive
            ? { directive: settings.directive }
            : {}),
        retain: settings.retain,
      });
    },
    [pushNotice, runCompact, session],
  );

  const confirmSlashClear = useCallback(() => {
    setSlashClearOpen(false);
    if (session.prepSessionId !== null) void manage.clearSession(session.prepSessionId);
  }, [manage, session.prepSessionId]);

  const cancelSlashClear = useCallback(() => {
    setSlashClearOpen(false);
  }, []);

  return {
    messages,
    setMessages,
    input,
    setInput,
    loading,
    /** True while a manual compaction is in flight for the viewed session. */
    compacting: compactingSid !== null && compactingSid === session.prepSessionId,
    busySids,
    stopSession: handleStop,
    starting: session.starting,
    restoring: session.restoring,
    prepError: session.prepError,
    switchError: session.switchError,
    switchFailedId: session.switchFailedId,
    clearSwitchError: session.clearSwitchError,
    prepSessionId: session.prepSessionId,
    resumes: resources.resumes,
    resumeId: resources.resumeId,
    setResumeId: resources.setResumeId,
    resumeLoadError: resources.resumeLoadError,
    sessions: resources.sessions,
    askDialog,
    chatModels: resources.chatModels,
    selectedModelId: resources.selectedModelId,
    setSelectedModelId: resources.setSelectedModelId,
    defaultChatProfile: resources.defaultChatProfile,
    effort: resources.effort,
    setEffort: resources.setEffort,
    tokenUsage: session.tokenUsage,
    usage: session.usage,
    contextBuckets: session.contextBuckets,
    contextTotal: session.contextTotal,
    estimatedPrompt: session.estimatedPrompt,
    showJump: scroll.showJump,
    chatScrollRef: scroll.chatScrollRef,
    contentRef: scroll.contentRef,
    handleSend,
    handleStop,
    pendingRefs,
    addRef,
    removeRef,
    handleSlashCommand,
    slashClearOpen,
    confirmSlashClear,
    cancelSlashClear,
    handleAskAnswer,
    handleQuickPrompt,
    handleNewSession: session.handleNewSession,
    handleScroll: scroll.handleScroll,
    jumpToBottom: scroll.jumpToBottom,
    switchSession: session.switchSession,
    reloadMessages: session.reloadMessages,
    backendCount,
    startPrep: session.startPrep,
    setAskDialog,
    deleteSession: manage.deleteSession,
    archiveSession: manage.archiveSession,
    clearSession: manage.clearSession,
    messageActions: {
      onExport: actions.handleExport,
      onFork: actions.handleFork,
      onRegenerate: actions.handleRegenerate,
      onRate: actions.openRate,
      onRetract: actions.handleRetract,
    },
    compactionActions: {
      onForkFromPoint: actions.handleCompactionFork,
      onOpenBackup: actions.handleCompactionOpen,
      onReload: () => {
        const id = session.prepSessionId;
        if (id !== null) void session.reloadMessages(id);
      },
      onRegenerate: () => {
        const id = session.prepSessionId;
        if (id === null) return;
        const settings = resolveCompactParams();
        void runCompact(id, { ...settings, backup: false });
      },
    },
    archiveGroups,
    rateTarget: actions.rateTarget,
    rateBusy: actions.rateBusy,
    closeRate: actions.closeRate,
    submitRate: actions.submitRate,
  };
}
