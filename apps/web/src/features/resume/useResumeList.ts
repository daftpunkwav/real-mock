/**
 * @file useResumeList
 * @description Resume page facade: compose collection + mutations.
 *
 * Responsibilities:
 * - Wire useResumeCollection + useResumeMutations
 * - Report settled background parses (degraded / failed) via toast
 * - Expose a stable API for the resume page
 *
 * Must not render UI; page components consume the returned API.
 * See ResumeList item for ConfirmDialog ownership.
 */

"use client";

import { useRef } from "react";
import { toast } from "@/components/Toast";
import { getTranslator } from "@/i18n/resolve";
import { useResumeCollection } from "./useResumeCollection";
import { useResumeMutations } from "./useResumeMutations";
import type { ResumeItem } from "./resumeNormalize";

export function useResumeList() {
  // Tracks which pending rows have already been reported so a settled row is
  // toasted exactly once (poll reloads and manual reloads both pass here).
  const reportedRef = useRef<Set<number>>(new Set());
  // Rows seen as pending during this session: only these earn the degraded
  // toast, so resumes that were already degraded on first load never
  // re-announce old history on every page visit.
  const sawPendingRef = useRef<Set<number>>(new Set());

  const onParseSettled = (rows: ResumeItem[]) => {
    const t = getTranslator("resume");
    for (const row of rows) {
      if (row.parse_status === "pending") {
        sawPendingRef.current.add(row.id);
        reportedRef.current.delete(row.id);
        continue;
      }
      if (reportedRef.current.has(row.id)) continue;
      if (row.parse_status === "failed") {
        reportedRef.current.add(row.id);
        toast.error(t("toast.parseFailed"), { durationMs: 8_000 });
      } else if (
        row.parse_status === "done" &&
        row.parsed_profile.parse_degraded &&
        sawPendingRef.current.has(row.id)
      ) {
        reportedRef.current.add(row.id);
        toast.warning(t("toast.uploadedFallback"), { durationMs: 6_000 });
      }
    }
  };

  const collection = useResumeCollection(onParseSettled);
  const mutations = useResumeMutations({
    resumes: collection.resumes,
    load: collection.load,
    setPreviewId: (id: number) => collection.setPreviewId(id),
  });

  return {
    ...collection,
    ...mutations,
  };
}
