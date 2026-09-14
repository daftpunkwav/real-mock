/**
 * @file profile types
 * @description Shared TypeScript types for profile form sections.
 *
 * Responsibilities:
 * - ProfilePatch / ProfileSectionProps for section components
 *
 * Must not import React or HTTP clients.
 */

import type { UserProfileResponse as UserProfile } from "@/lib/api/contract";
import type { RequiredKey } from "./profileRequired";

/** Partial updater; clearing a required key's error is handled by the form facade. */
export type ProfilePatch = <K extends keyof UserProfile>(
  key: K,
  value: UserProfile[K],
) => void;

/** Shared props for form sections: data + patch + required-error highlighter. */
export interface ProfileSectionProps {
  profile: UserProfile;
  patch: ProfilePatch;
  requiredError: (key: RequiredKey) => boolean;
}
