/**
 * @file useResumeCollection
 * @description Local resume list state: load, preview selection, derived analysis.
 *
 * Responsibilities:
 * - Load the list with AbortSignal (cancel stale loads on retry/unmount)
 * - Poll while any row is still parsing (parse_status="pending") so the UI
 *   converges without a manual refresh; stops when visible or after a budget
 * - Pick a stable preview id (keep current → active → first)
 * - Expose the selected row and its narrowed analysis
 * - Support silent reloads after mutations (no page-level spinner; keep the list on failure)
 *
 * Must not own upload/analyze/activate/delete messaging.
 */

"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { formatApiError, isRequestAborted } from "@/lib/api/base";
import { resumeHttp as api } from "@/lib/api/clients";
import { getTranslator } from "@/i18n/resolve";
import { asAnalysis } from "./analysisFormat";
import { normalizeResumeList, type ResumeItem } from "./resumeNormalize";
import { pickPreviewId } from "./resumeSelection";

export type ResumeLoadOptions = {
  /** Skip the full-page spinner and keep the current list if the request fails. */
  silent?: boolean;
};

/** Poll cadence while at least one row is parsing. */
const PARSE_POLL_INTERVAL_MS = 4_000;
/** Hard stop for polling (~20 min); a manual refresh re-arms it. */
const PARSE_POLL_MAX_MS = 20 * 60_000;

export function useResumeCollection(onParseSettled?: (rows: ResumeItem[]) => void) {
  const [resumes, setResumes] = useState<ResumeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [previewId, setPreviewId] = useState<number | null>(null);
  const loadAbortRef = useRef<AbortController | null>(null);
  // Guards: only one poll request in flight; poller state readable in timers.
  const pollInFlightRef = useRef(false);
  const pollStartRef = useRef<number>(0);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const settledRef = useRef(onParseSettled);
  settledRef.current = onParseSettled;

  const load = (options?: ResumeLoadOptions) => {
    const silent = options?.silent === true;
    loadAbortRef.current?.abort();
    const controller = new AbortController();
    loadAbortRef.current = controller;
    if (!silent) {
      setLoading(true);
      setLoadError("");
    }
    return api
      .listResumes({ signal: controller.signal })
      .then((list) => {
        if (controller.signal.aborted) return;
        const next = normalizeResumeList(list);
        setResumes(next);
        setPreviewId((prev) => pickPreviewId(next, prev));
        settledRef.current?.(next);
      })
      .catch((e) => {
        if (controller.signal.aborted || isRequestAborted(e)) return;
        if (silent) throw e;
        setLoadError(
          e instanceof Error ? formatApiError(e) : getTranslator("resume")("hook.loadFailed"),
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
  };

  useEffect(() => {
    load();
    return () => loadAbortRef.current?.abort();
  }, []);

  // Background-parse polling: one silent reload every PARSE_POLL_INTERVAL_MS
  // while any row is pending; a hidden tab and poll failures both just skip a
  // tick. `hasPending` re-runs the effect, so the timer self-cleans when the
  // last row settles; the budget only resets once nothing is pending anymore.
  const hasPending = resumes.some((row) => row.parse_status === "pending");
  const hasPendingRef = useRef(hasPending);
  hasPendingRef.current = hasPending;

  useEffect(() => {
    if (!hasPending) {
      pollStartRef.current = 0;
      return;
    }
    if (pollStartRef.current === 0) pollStartRef.current = Date.now();
    // Cleared on cleanup so a tick finishing after unmount cannot re-arm the
    // timer — otherwise the schedule chain outlives the hook and keeps
    // polling (until the budget expires) with no component left to update.
    let alive = true;

    const schedule = () => {
      if (!alive) return;
      if (pollTimerRef.current) return;
      if (!hasPendingRef.current) return;
      if (Date.now() - pollStartRef.current > PARSE_POLL_MAX_MS) return;
      pollTimerRef.current = setTimeout(tick, PARSE_POLL_INTERVAL_MS);
    };

    const tick = async () => {
      pollTimerRef.current = null;
      if (typeof document !== "undefined" && document.hidden) {
        schedule();
        return;
      }
      if (pollInFlightRef.current) {
        schedule();
        return;
      }
      pollInFlightRef.current = true;
      try {
        const list = await api.listResumes();
        const next = normalizeResumeList(list);
        setResumes(next);
        setPreviewId((prev) => pickPreviewId(next, prev));
        settledRef.current?.(next);
      } catch {
        // Transient poll failure: keep the current list, the next tick retries.
      } finally {
        pollInFlightRef.current = false;
      }
      schedule();
    };

    pollTimerRef.current = setTimeout(tick, PARSE_POLL_INTERVAL_MS);
    return () => {
      alive = false;
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [hasPending]);

  const previewResume = useMemo(
    () => resumes.find((row) => row.id === previewId) ?? null,
    [resumes, previewId],
  );

  const analysis = useMemo(
    () => (previewResume ? asAnalysis(previewResume.analysis) : null),
    [previewResume],
  );

  return {
    resumes,
    loading,
    loadError,
    previewId,
    previewResume,
    analysis,
    setPreviewId,
    load,
  };
}
