"use client";

/**
 * @file usePrepChat.ts
 * @description Prep chat composition root: wires resources, session state,
 * send pipeline, message actions, and session management into one view-model.
 * Exposes per-session busy state so background generations stay visible and
 * stoppable from the session list.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocale } from "@/i18n";
import { getTranslator } from "@/i18n/resolve";
import type { PrepSessionSummary } from "@/lib/api/contract";
import type { AskUserDialog, PrepUsageStats } from "@/types";
import type { PrepChatMessage } from "../types";
import type { RateSubmit } from "../components/RateModal";
import type { SlashName } from "../slashCommands";
import { parseCompactArgs } from "../slashCommands";
import { resolveCompactParams } from "@/lib/compactThreshold";
import { type ArchivedGroup } from "../compactionArchive";
import type { PendingSessionRef } from "../sessionRefs";
import { activeStreamIds, subscribeStreams } from "../streamRegistry";
import { usePrepCompact } from "./usePrepCompact";
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
  reportedContext: { prompt: number; completion: number };
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
    onSaveEdit: (sessionId: number, text: string) => Promise<void>;
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

  /** Append a local-only notice (never persisted, never in context). */
  const pushNotice = useCallback(
    (text: string) => {
      setMessages((m) => [...m, { id: nextMsgId("n"), role: "assistant", content: text, localOnly: true }]);
    },
    [nextMsgId],
  );

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

  const {
    archiveGroups,
    compactingSid,
    isCompacting: isCompactingSession,
    runCompact,
    saveSummaryEdit,
  } = usePrepCompact({
    viewedId: session.prepSessionId,
    messages,
    pushNotice,
    backendCount,
    refreshSessions: resources.refreshSessions,
    reloadMessages: session.reloadMessages,
  });

  const { handleStop, handleAskAnswer, handleQuickPrompt, sendMessage, consumeBackgroundUsage } = usePrepSend({
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
    syncReportedContext: session.syncReportedContext,
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
    isCompacting: isCompactingSession,
  });

  const actions = usePrepMessageActions({
    prepSessionId: session.prepSessionId,
    messages,
    setMessages,
    stopStream: handleStop,
    sendMessage,
    switchSession: session.switchSession,
    setBackendCount,
    backendCount,
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
  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || !session.prepSessionId) return;
    const ids = pendingRefs.map((r) => r.id);
    const accepted = await sendMessage(text, undefined, false, ids.length > 0 ? { contextSessionIds: ids } : undefined);
    // A refused send (compacting guard or full queue) keeps both the input
    // and the chips, so the references survive until the next accepted send.
    if (accepted) setPendingRefs([]);
  }, [input, pendingRefs, sendMessage, session.prepSessionId]);

  // Background-turn usage catch-up: turns finalized while away recorded their
  // deltas/totals off-view; apply them once when the session is viewed.
  // Server totals win; deltas only cover turns without a done envelope.
  const viewedId = session.prepSessionId;
  const reloadMessages = session.reloadMessages;
  useEffect(() => {
    if (viewedId === null) return;
    const pending = consumeBackgroundUsage(viewedId);
    if (pending.totals) {
      session.syncUsage(pending.totals);
    } else if (pending.deltas) {
      session.mergeUsage(pending.deltas);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewedId]);

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

  // Stable action objects: memoized chat bubbles compare props shallowly, so
  // rebuilt-per-render handlers would re-render every message on each token.
  const messageActions = useMemo(
    () => ({
      onExport: actions.handleExport,
      onFork: actions.handleFork,
      onRegenerate: actions.handleRegenerate,
      onRate: actions.openRate,
      onRetract: actions.handleRetract,
    }),
    [
      actions.handleExport,
      actions.handleFork,
      actions.handleRegenerate,
      actions.openRate,
      actions.handleRetract,
    ],
  );

  const compactionActions = useMemo(
    () => ({
      onForkFromPoint: actions.handleCompactionFork,
      onOpenBackup: actions.handleCompactionOpen,
      onSaveEdit: saveSummaryEdit,
      onReload: () => {
        if (viewedId !== null) void reloadMessages(viewedId);
      },
      onRegenerate: () => {
        if (viewedId === null) return;
        const settings = resolveCompactParams();
        void runCompact(viewedId, { ...settings, backup: false });
      },
    }),
    [
      actions.handleCompactionFork,
      actions.handleCompactionOpen,
      saveSummaryEdit,
      viewedId,
      reloadMessages,
      runCompact,
    ],
  );

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
    reportedContext: session.reportedContext,
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
    messageActions,
    compactionActions,
    archiveGroups,
    rateTarget: actions.rateTarget,
    rateBusy: actions.rateBusy,
    closeRate: actions.closeRate,
    submitRate: actions.submitRate,
  };
}
