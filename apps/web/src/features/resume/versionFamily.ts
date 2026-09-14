/**
 * @file versionFamily.ts
 * @description Pure helpers for resume-family identity, grouping, and version-cap checks.
 *
 * Must not import React, HTTP, or i18n.
 */

import { MAX_RESUME_VERSIONS } from "./resumeLimits";
import type { ResumeItem } from "./resumeNormalize";

export type ResumeFamilyGroup = {
  familyId: number;
  members: ResumeItem[];
};

export function familyIdOf(row: { id: number; family_id?: number }): number {
  return Number(row.family_id) > 0 ? Number(row.family_id) : row.id;
}

/** Group rows by family; families newest-first; members by version ascending. */
export function groupResumeFamilies(rows: ResumeItem[]): ResumeFamilyGroup[] {
  const buckets = new Map<number, ResumeItem[]>();
  for (const row of rows) {
    const fid = familyIdOf(row);
    const list = buckets.get(fid) ?? [];
    list.push(row);
    buckets.set(fid, list);
  }
  const groups: ResumeFamilyGroup[] = [...buckets.entries()].map(([familyId, members]) => ({
    familyId,
    members: [...members].sort((a, b) => (Number(a.version_n) || 1) - (Number(b.version_n) || 1)),
  }));
  groups.sort((a, b) => {
    const aLatest = a.members[a.members.length - 1]?.created_at ?? "";
    const bLatest = b.members[b.members.length - 1]?.created_at ?? "";
    return aLatest < bLatest ? 1 : aLatest > bLatest ? -1 : 0;
  });
  return groups;
}

export function isLatestIdle(group: ResumeFamilyGroup, row: ResumeItem): boolean {
  const latest = group.members[group.members.length - 1];
  return latest?.id === row.id && !row.is_active && group.members.length > 1;
}

/** Single source for the version-cap rule (hook toast gate + list-item disable). */
export function canAddVersion(memberCount: number, maxVersions: number = MAX_RESUME_VERSIONS): boolean {
  return memberCount < maxVersions;
}
