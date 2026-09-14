/**
 * @file profileCompletion
 * @description Completeness stats, blank detection, and editable-content equality.
 *
 * Responsibilities:
 * - Detect missing required keys
 * - Count optional filled fields from the profileFields catalog
 * - Compute completion percentage
 * - Tell whether every update-contract field is blank (clear-button gate)
 * - Compare two snapshots by editable fields only (dirty detection)
 *
 * Depends on profileFields + techDomains cleaner only. Ignores id / updated_at
 * when comparing content so a server timestamp cannot mark the form dirty.
 */

import type { UserProfileResponse as UserProfile } from "@/lib/api/contract";
import {
  OPTIONAL_COMPLETION_KEYS,
  PROFILE_UPDATE_KEYS,
  REQUIRED_KEYS,
  type RequiredKey,
} from "./profileFields";
import { cleanTechDomains } from "./techDomains";

export { OPTIONAL_COMPLETION_KEYS };

export interface ProfileCompletionStats {
  filledDomains: string[];
  requiredMissing: RequiredKey[];
  requiredDone: number;
  optionalDone: number;
  completionPct: number;
}

function filledDomainsOf(profile: UserProfile): string[] {
  return cleanTechDomains(profile.tech_domains);
}

function isFieldFilled(
  profile: UserProfile,
  key: keyof UserProfile,
  filledDomains: string[],
): boolean {
  if (key === "tech_domains") return filledDomains.length > 0;
  const value = profile[key];
  return typeof value === "string" ? value.trim().length > 0 : Boolean(value);
}

function requiredMissingOf(profile: UserProfile, filledDomains: string[]): RequiredKey[] {
  return REQUIRED_KEYS.filter((key) => !isFieldFilled(profile, key, filledDomains));
}

/** True when every update-contract field is blank (including inCompletion:false optionals). */
export function isProfileBlank(profile: UserProfile): boolean {
  const filledDomains = filledDomainsOf(profile);
  return PROFILE_UPDATE_KEYS.every((key) => !isFieldFilled(profile, key, filledDomains));
}

/**
 * True when editable fields match. Trailing spaces and domain order count as
 * differences; id / updated_at do not (those are server-owned).
 */
export function isProfileContentEqual(a: UserProfile, b: UserProfile): boolean {
  for (const key of PROFILE_UPDATE_KEYS) {
    if (key === "tech_domains") {
      const left = a.tech_domains;
      const right = b.tech_domains;
      if (left.length !== right.length) return false;
      for (let i = 0; i < left.length; i++) {
        if (left[i] !== right[i]) return false;
      }
      continue;
    }
    if (a[key] !== b[key]) return false;
  }
  return true;
}

export function completionStatsOf(profile: UserProfile | null): ProfileCompletionStats {
  if (!profile) {
    return {
      filledDomains: [],
      requiredMissing: [...REQUIRED_KEYS],
      requiredDone: 0,
      optionalDone: 0,
      completionPct: 0,
    };
  }
  const filledDomains = filledDomainsOf(profile);
  const requiredMissing = requiredMissingOf(profile, filledDomains);
  const requiredDone = REQUIRED_KEYS.length - requiredMissing.length;
  const optionalDone = OPTIONAL_COMPLETION_KEYS.filter((key) =>
    isFieldFilled(profile, key, filledDomains),
  ).length;
  const totalTracked = REQUIRED_KEYS.length + OPTIONAL_COMPLETION_KEYS.length;
  const completion = requiredDone + optionalDone;
  return {
    filledDomains,
    requiredMissing,
    requiredDone,
    optionalDone,
    completionPct: Math.round((completion / totalTracked) * 100),
  };
}
