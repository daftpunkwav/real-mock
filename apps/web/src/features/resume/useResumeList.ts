/**
 * @file useResumeList
 * @description Resume page facade: compose collection + mutations.
 *
 * Responsibilities:
 * - Wire useResumeCollection + useResumeMutations
 * - Expose a stable API for the resume page
 *
 * Must not render UI; page components consume the returned API.
 * See ResumeList item for ConfirmDialog ownership.
 */

"use client";

import { useResumeCollection } from "./useResumeCollection";
import { useResumeMutations } from "./useResumeMutations";

export function useResumeList() {
  const collection = useResumeCollection();
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
