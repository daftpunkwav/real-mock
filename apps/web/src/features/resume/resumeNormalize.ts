/**
 * @file resumeNormalize
 * @description Coerce OpenAPI ResumeResponse / CandidateProfile into UI-safe shapes.
 *
 * Responsibilities:
 * - Fill missing parsed_profile arrays so list/preview cards never see undefined
 *
 * Must not import React or HTTP clients.
 */

import type { CandidateProfile, ResumeResponse } from "@/lib/api/contract";

/** Project blobs from the parser are free-form objects; UI reads name/description. */
export interface ParsedProject {
  name?: string;
  description?: string;
  [key: string]: unknown;
}

export interface ParsedProfile {
  name: string;
  education: Record<string, unknown>[];
  work_experience: Record<string, unknown>[];
  skills: string[];
  projects: ParsedProject[];
  summary: string;
  parse_degraded: boolean;
}

/** Resume row after profile coerce; analysis stays an untyped dict until asAnalysis. */
export type ResumeItem = Omit<ResumeResponse, "parsed_profile"> & {
  parsed_profile: ParsedProfile;
  family_id: number;
  version_n: number;
};

function lineageOf(row: ResumeResponse): { family_id: number; version_n: number } {
  const extra = row as ResumeResponse & { family_id?: number; version_n?: number };
  return {
    family_id: Number(extra.family_id) > 0 ? Number(extra.family_id) : row.id,
    version_n: Math.max(1, Number(extra.version_n) || 1),
  };
}

export function normalizeParsedProfile(
  raw: CandidateProfile | null | undefined,
): ParsedProfile {
  return {
    name: raw?.name ?? "",
    education: (raw?.education ?? []) as Record<string, unknown>[],
    work_experience: (raw?.work_experience ?? []) as Record<string, unknown>[],
    skills: raw?.skills ?? [],
    projects: (raw?.projects ?? []) as ParsedProject[],
    summary: raw?.summary ?? "",
    parse_degraded: raw?.parse_degraded === true,
  };
}

export function normalizeResume(row: ResumeResponse): ResumeItem {
  return {
    ...row,
    ...lineageOf(row),
    parsed_profile: normalizeParsedProfile(row.parsed_profile),
  };
}

export function normalizeResumeList(rows: ResumeResponse[] | null | undefined): ResumeItem[] {
  return (rows ?? []).map(normalizeResume);
}
