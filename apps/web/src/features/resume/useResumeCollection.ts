/**
 * @file useResumeCollection
 * @description Local resume list state: load, preview selection, derived analysis.
 *
 * Responsibilities:
 * - Load the list with AbortSignal (cancel stale loads on retry/unmount)
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

export function useResumeCollection() {
  const [resumes, setResumes] = useState<ResumeItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [previewId, setPreviewId] = useState<number | null>(null);
  const loadAbortRef = useRef<AbortController | null>(null);

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
