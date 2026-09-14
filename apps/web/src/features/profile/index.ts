/**
 * @file profile feature barrel
 * @description Public exports for the profile feature consumed by app routes.
 *
 * Responsibilities:
 * - Re-export page-facing hooks, section components, and shared types/rules
 *
 * Field metadata lives in profileFields.ts; this barrel re-exports derived constants.
 * Internal hooks (editor/save/nav) stay unexported to keep the public surface narrow.
 * Confirm dialogs live in `@/components/ConfirmDialog` — the page imports them there.
 */

export {
  PROFILE_FIELD_LIMITS,
  TECH_DOMAIN_ITEM_MAX,
  TECH_DOMAINS_MAX_COUNT,
} from "./profileLimits";
export { REQUIRED_KEYS, REQUIRED_LABELS, type RequiredKey } from "./profileRequired";
export {
  OPTIONAL_COMPLETION_KEYS,
  completionStatsOf,
  type ProfileCompletionStats,
} from "./profileCompletion";
export { cleanTechDomains } from "./techDomains";
export { buildProfileUpdate } from "./buildProfileUpdate";
export { useProfileForm } from "./useProfileForm";
export type { ProfilePatch, ProfileSectionProps } from "./types";
export { PageHead } from "./components/PageHead";
export { BasicInfoSection } from "./components/BasicInfoSection";
export { EducationSection } from "./components/EducationSection";
export { JobIntentSection } from "./components/JobIntentSection";
export { OnlineIdentitySection } from "./components/OnlineIdentitySection";
export { SkillsSection } from "./components/SkillsSection";
export { CompletionCard } from "./components/CompletionCard";
export { PreviewCard } from "./components/PreviewCard";
