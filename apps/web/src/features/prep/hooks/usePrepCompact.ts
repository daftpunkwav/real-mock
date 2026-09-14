"use client";

/**
 * @file usePrepCompact.ts
 * @description Manual compaction orchestration: archive-aware /compact runs,
 * summary-edit saves (both with one optimistic-concurrency retry), per-session
 * in-flight guards, and the display-only archive of folded turns (the backend
 * keeps only the summary).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { getTranslator } from "@/i18n/resolve";
import { formatTokens } from "@/components/ModelControls";
import { prepCoachHttp as api } from "@/lib/api/clients";
import { ApiError, formatApiError } from "@/lib/api/base";
import type { PrepChatMessage } from "../types";
import { loadArchive, pushArchivedGroup, toArchivedCopy, type ArchivedGroup } from "../compactionArchive";
import { hasActiveStream } from "../streamRegistry";

export interface CompactRunParams {
  intensity: "light" | "balanced" | "aggressive";
  directive?: string;
  retain: number;
  backup?: boolean;
}

export function usePrepCompact(opts: {
  /** Currently viewed session id (display archive follows it). */
  viewedId: number | null;
  /** Current view messages (folded range is archived for display). */
  messages: PrepChatMessage[];
  /** Append a local-only notice (never persisted, never in context). */
  pushNotice: (text: string) => void;
  /** Tracked backend length (optimistic-concurrency guard source). */
  backendCount: (sid: number) => number | undefined;
  /** Refresh the session list (totals change after compaction). */
  refreshSessions: () => void;
  /** Reload a session's history in place (post-compact refresh). */
  reloadMessages: (id: number) => Promise<void>;
}) {
  const { viewedId, messages, pushNotice, backendCount, refreshSessions, reloadMessages } = opts;
  /** Display-only archive of folded turns (backend keeps only the summary). */
  const [archiveGroups, setArchiveGroups] = useState<ArchivedGroup[]>([]);
  /** Session with a manual compaction in flight (blocks sends + shows progress). */
  const [compactingSid, setCompactingSid] = useState<number | null>(null);
  /** Ref mirror of compactingSid: stable guard for callbacks without re-binding. */
  const compactingRef = useRef(new Set<number>());

  // Display archive follows the viewed session (loaded once per switch).
  useEffect(() => {
    if (viewedId === null) {
      setArchiveGroups([]);
      return;
    }
    setArchiveGroups(loadArchive(viewedId)?.groups ?? []);
  }, [viewedId]);

  /**
   * Archive-aware manual compaction shared by /compact and card regenerate:
   * fold the reported range into a display group, reload backend truth
   * (indices shift on rewrite), and bring the newest card into view.
   */
  const runCompactAttempt = useCallback(
    async (sid: number, params: CompactRunParams) => {
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
          refreshSessions();
          // Reload backend truth so retained-tail indices match the rewrite.
          await reloadMessages(sid);
          requestAnimationFrame(() => {
            const cards = document.querySelectorAll("[data-compaction-card]");
            cards[cards.length - 1]?.scrollIntoView({ block: "center" });
          });
        } catch (e) {
          // Stale count guard fired (background/stopped turns moved history):
          // resync once from the backend and retry once, then report.
          if (!retried && e instanceof ApiError && e.code === "A3003") {
            await reloadMessages(sid);
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
    [backendCount, messages, pushNotice, refreshSessions, reloadMessages],
  );

  const runCompact = useCallback(
    async (sid: number, params: CompactRunParams) => {
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

  /**
   * Save an edited compaction summary with one optimistic-concurrency retry:
   * a stale count (background turn landed mid-edit) resyncs from the backend
   * and retries once with the fresh count. Throws on final failure for the
   * caller to toast.
   */
  const saveSummaryEdit = useCallback(
    async (sid: number, text: string) => {
      const attempt = async (retried: boolean): Promise<void> => {
        try {
          await api.updateSummary(sid, text, backendCount(sid));
          await reloadMessages(sid);
        } catch (e) {
          if (!retried && e instanceof ApiError && e.code === "A3003") {
            await reloadMessages(sid);
            await attempt(true);
            return;
          }
          throw e;
        }
      };
      await attempt(false);
    },
    [backendCount, reloadMessages],
  );

  const isCompacting = useCallback((sid: number) => compactingRef.current.has(sid), []);

  return { archiveGroups, compactingSid, isCompacting, runCompact, saveSummaryEdit };
}
