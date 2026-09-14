/**
 * @file previewRoute.ts
 * @description Resume preview page (`/resume/preview`) query contract and URL builders.
 *
 * Responsibilities:
 * - Stable query key names
 * - build / parse round-trip including non-ASCII filenames
 *
 * Must not import React or i18n: callers inject the localized fallback.
 */

export const RESUME_PREVIEW_QUERY = {
  id: "id",
  name: "name",
  type: "type",
} as const;

export interface ResumePreviewParams {
  /** Resume id; invalid links parse as 0 — callers treat falsy as missing. */
  id: number;
  name: string;
  type: string;
}

export function buildResumePreviewUrl({ id, name, type }: ResumePreviewParams): string {
  const params = new URLSearchParams({
    [RESUME_PREVIEW_QUERY.id]: String(id),
    [RESUME_PREVIEW_QUERY.name]: name,
    [RESUME_PREVIEW_QUERY.type]: type,
  });
  return `/resume/preview?${params.toString()}`;
}

export function parseResumePreviewParams(
  search: Pick<URLSearchParams, "get">,
  nameFallback = "",
): ResumePreviewParams {
  return {
    id: Number(search.get(RESUME_PREVIEW_QUERY.id)) || 0,
    name: search.get(RESUME_PREVIEW_QUERY.name) ?? nameFallback,
    type: (search.get(RESUME_PREVIEW_QUERY.type) ?? "").toLowerCase(),
  };
}
