/**
 * @file buildProfileUpdate
 * @description Map a profile response/form snapshot to a PUT body.
 *
 * Responsibilities:
 * - Emit only UserProfileUpdate fields from the profileFields catalog
 * - Drop read-only keys (id, updated_at, future extras on Response)
 * - Normalize tech_domains before send
 *
 * Must not call the network or touch React state.
 */

import type { UserProfileResponse, UserProfileUpdate } from "@/lib/api/contract";
import { PROFILE_UPDATE_KEYS } from "./profileFields";
import { cleanTechDomains } from "./techDomains";

/** Catalog-driven whitelist: Response→Update stays complete as PROFILE_FIELDS grows. */
export function buildProfileUpdate(profile: UserProfileResponse): UserProfileUpdate {
  const payload = {} as UserProfileUpdate;
  for (const key of PROFILE_UPDATE_KEYS) {
    if (key === "tech_domains") {
      payload.tech_domains = cleanTechDomains(profile.tech_domains);
      continue;
    }
    const value = profile[key];
    payload[key] = (typeof value === "string" ? value : "") as UserProfileUpdate[typeof key];
  }
  return payload;
}
