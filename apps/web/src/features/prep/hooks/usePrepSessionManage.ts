"use client";

/**
 * @file usePrepSessionManage.ts
 * @description Prep session management: delete, archive/restore, and clear
 * messages. Destructive actions stop the live stream first so a stopped
 * partial cannot resurrect pruned history.
 */

import { toast } from "@/components/Toast";
import { prepCoachHttp as api } from "@/lib/api/clients";
import { formatApiError } from "@/lib/api/base";
import { getTranslator } from "@/i18n/resolve";
import type { AskUserDialog } from "@/types";
import { abortStream, hasActiveStream, STREAM_STOP_GRACE_MS } from "../streamRegistry";
import { clearArchive } from "../compactionArchive";
import type { PrepChatMessage } from "../types";

/** Re-exported for call sites that need the same stop-then-mutate pacing. */
export { STREAM_STOP_GRACE_MS as PREP_STOP_GRACE_MS };

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export function usePrepSessionManage(opts: {
  prepSessionId: number | null;
  setMessages: React.Dispatch<React.SetStateAction<PrepChatMessage[]>>;
  setAskDialog: React.Dispatch<React.SetStateAction<AskUserDialog | null>>;
  nextMsgId: (prefix: string) => string;
  /** Abort the viewed session's live stream, if any. */
  stopStream: () => void;
  startPrep: () => Promise<number | null>;
  setBackendCount: (sid: number, n: number) => void;
  refreshSessions: () => void;
}) {
  const {
    prepSessionId,
    setMessages,
    setAskDialog,
    nextMsgId,
    stopStream,
    startPrep,
    setBackendCount,
    refreshSessions,
  } = opts;

  const fail = (key: "sessions.deleteFailed" | "sessions.archiveFailed" | "sessions.clearFailed", err: unknown) => {
    const t = getTranslator("prep");
    toast.error(err instanceof Error ? formatApiError(err) : t(key));
  };

  /** Stop a session's live stream (if any) and let its stopped turn land first. */
  const haltSession = async (id: number) => {
    if (!hasActiveStream(id)) return;
    if (id === prepSessionId) stopStream();
    else abortStream(id);
    await wait(STREAM_STOP_GRACE_MS);
  };

  const deleteSession = async (id: number) => {
    try {
      await haltSession(id);
      await api.deleteSession(id);
      clearArchive(id);
      refreshSessions();
      if (id === prepSessionId) {
        setAskDialog(null);
        await startPrep();
      }
    } catch (err) {
      fail("sessions.deleteFailed", err);
    }
  };

  const archiveSession = async (id: number, archived: boolean) => {
    try {
      await api.archiveSession(id, archived);
      refreshSessions();
    } catch (err) {
      fail("sessions.archiveFailed", err);
    }
  };

  const clearSession = async (id: number) => {
    const t = getTranslator("prep");
    try {
      await haltSession(id);
      await api.truncateMessages(id, 0);
      clearArchive(id);
      refreshSessions();
      if (id === prepSessionId) {
        setBackendCount(id, 0);
        setAskDialog(null);
        setMessages([
          { id: nextMsgId("a"), role: "assistant", content: t("sessions.welcome"), localOnly: true },
        ]);
      }
    } catch (err) {
      fail("sessions.clearFailed", err);
    }
  };

  return { deleteSession, archiveSession, clearSession };
}
