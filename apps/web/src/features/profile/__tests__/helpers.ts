/**
 * @file helpers.ts
 * @description Shared fixtures for profile feature unit tests.
 *
 * makeProfile fills every PROFILE_UPDATE_KEYS entry so a new catalog field
 * cannot slip through as undefined in fixtures.
 */

import type { UserProfileResponse, UserProfileUpdate } from "@/lib/api/contract";
import { PROFILE_UPDATE_KEYS } from "../profileFields";

/** Blank profile: empty strings/arrays; tests override fields as needed. */
export function makeProfile(overrides: Partial<UserProfileResponse> = {}): UserProfileResponse {
  const profile = {
    id: 1,
    updated_at: null,
  } as UserProfileResponse;
  for (const key of PROFILE_UPDATE_KEYS) {
    if (key === "tech_domains") {
      profile.tech_domains = [];
      continue;
    }
    profile[key] = "" as UserProfileUpdate[typeof key];
  }
  return { ...profile, ...overrides };
}
