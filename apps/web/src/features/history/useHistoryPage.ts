"use client";

/**
 * History page load domain: session list via recordsHttp, default selection,
 * aggregate stats, and LoadError retry with request sequencing.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { interviewHttp, recordsHttp } from "@/lib/api/clients";
import { getTranslator } from "@/i18n/resolve";
import { toast } from "@/components/Toast";
import {
  buildNextRoundIndex,
  selectEligibleProcesses,
  type EligibleProcess,
} from "@/lib/interviewProcesses";
import type { SessionHistoryItem } from "@/types/domains/records";

/** History page: sessions + default selection + stats + LoadError retry. */
export function useHistoryPage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [nextRoundIndex, setNextRoundIndex] = useState<Record<number, EligibleProcess>>({});
  const [startingNext, setStartingNext] = useState(false);
  const seqRef = useRef(0);

  const load = useCallback(async () => {
    const seq = ++seqRef.current;
    setLoading(true);
    setLoadError(null);
    try {
      const [list, processes] = await Promise.all([
        recordsHttp.listSessions(),
        interviewHttp
          .listProcesses()
          .then(selectEligibleProcesses)
          .catch(() => []),
      ]);
      if (seq !== seqRef.current) return;
      setSessions(list);
      setNextRoundIndex(buildNextRoundIndex(processes));
      const firstCompleted = list.find((s) => s.status === "completed");
      const fallback = list[0];
      setSelectedId(firstCompleted?.id ?? fallback?.id ?? null);
    } catch (e) {
      if (seq !== seqRef.current) return;
      setLoadError(e instanceof Error ? e.message : getTranslator("history")("list.loadFailed"));
    } finally {
      if (seq !== seqRef.current) return;
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const startNextRound = useCallback(
    async (processId: number) => {
      const process = nextRoundIndex[processId];
      if (!process || startingNext) return;
      const t = getTranslator("history");
      setStartingNext(true);
      try {
        const session = await interviewHttp.createNextRound(processId);
        router.push(`/interview/${session.id}`);
      } catch (e) {
        toast.error(e instanceof Error ? e.message : t("detail.nextRoundFailed"));
      } finally {
        setStartingNext(false);
      }
    },
    [nextRoundIndex, startingNext, router],
  );

  const selected = useMemo(
    () => sessions.find((s) => s.id === selectedId) ?? null,
    [sessions, selectedId],
  );

  const stats = useMemo(
    () => ({
      total: sessions.length,
      completed: sessions.filter((s) => s.status === "completed").length,
      active: sessions.filter((s) => s.status === "active").length,
      avgScore: (() => {
        const scored = sessions.filter((s) => s.overall_score != null);
        if (scored.length === 0) return null;
        return Math.round(
          scored.reduce((sum, s) => sum + (s.overall_score ?? 0), 0) / scored.length,
        );
      })(),
    }),
    [sessions],
  );

  return {
    sessions,
    loading,
    loadError,
    selectedId,
    setSelectedId,
    selected,
    stats,
    nextRoundIndex,
    startingNext,
    startNextRound,
    load,
  };
}
