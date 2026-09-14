/**
 * @file useAnalyzeStream
 * @description Streaming deep-review orchestration for one resume at a time.
 *
 * Responsibilities:
 * - Cap parallel analyzes using the catalog
 * - Fold SSE progress events per resume id
 * - Toast analyzing / done / failed, then silently reload the collection
 *
 * Must not own uploads, activation, or deletion. Dialogs stay on list items.
 */

"use client";

import { useRef, useState } from "react";
import { formatApiError } from "@/lib/api/base";
import { resumeHttp as api } from "@/lib/api/clients";
import { toast } from "@/components/Toast";
import { getTranslator } from "@/i18n/resolve";
import { MAX_PARALLEL_ANALYZE } from "./resumeLimits";
import type { ResumeItem } from "./resumeNormalize";
import { applyAnalyzeEvent, type ReviewLiveState } from "./reviewProgress";

interface AnalyzeStreamDeps {
  resumes: ResumeItem[];
  load: (options?: { silent?: boolean }) => Promise<unknown>;
  setPreviewId: (id: number) => void;
}

export function useAnalyzeStream({ resumes, load, setPreviewId }: AnalyzeStreamDeps) {
  const [analyzingIds, setAnalyzingIds] = useState<number[]>([]);
  const [analyzeProgressById, setAnalyzeProgressById] = useState<Record<number, ReviewLiveState>>({});
  const [analyzeError, setAnalyzeError] = useState("");
  const analyzingIdsRef = useRef<number[]>([]);

  const handleAnalyze = (id: number) => {
    const t = getTranslator("resume");
    setAnalyzeError("");
    if (analyzingIdsRef.current.includes(id)) return;
    if (analyzingIdsRef.current.length >= MAX_PARALLEL_ANALYZE) {
      toast.error(t("toast.parallelLimit", { count: MAX_PARALLEL_ANALYZE }), {
        durationMs: 6000,
      });
      return;
    }
    const target = resumes.find((row) => row.id === id);
    setPreviewId(id);
    toast.clear();
    toast.info(
      target
        ? t("toast.analyzing", { name: target.filename, count: MAX_PARALLEL_ANALYZE })
        : t("toast.analyzingUnnamed", { count: MAX_PARALLEL_ANALYZE }),
      { persist: true },
    );
    analyzingIdsRef.current = [...analyzingIdsRef.current, id];
    setAnalyzingIds(analyzingIdsRef.current);
    setAnalyzeProgressById((prev) => ({ ...prev, [id]: { steps: [], timeline: [] } }));
    api
      .analyzeResumeStream(id, (event) => {
        setAnalyzeProgressById((prev) => ({
          ...prev,
          [id]: applyAnalyzeEvent(prev[id], event),
        }));
      })
      .then(async (data) => {
        // Persist is already committed; reload the list, then toast `data.score`.
        try {
          await load({ silent: true });
          toast.clear();
          toast.success(t("toast.analyzeDone", { score: data.score }), { durationMs: 8000 });
        } catch {
          toast.clear();
          toast.error(t("toast.listRefreshFailed"));
        }
      })
      .catch(async (err) => {
        // Swallow reload errors so the analyze failure toast is the only message.
        await load({ silent: true }).catch(() => undefined);
        const msg = err instanceof Error ? formatApiError(err) : t("toast.analyzeFailed");
        toast.clear();
        toast.error(msg, { durationMs: 10000 });
        setAnalyzeError(msg);
      })
      .finally(() => {
        analyzingIdsRef.current = analyzingIdsRef.current.filter((x) => x !== id);
        setAnalyzingIds(analyzingIdsRef.current);
        setAnalyzeProgressById((prev) => {
          const next = { ...prev };
          delete next[id];
          return next;
        });
      });
  };

  return {
    analyzingIds,
    analyzeProgressById,
    analyzeError,
    handleAnalyze,
  };
}
