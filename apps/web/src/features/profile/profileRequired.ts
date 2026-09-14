/**
 * @file profileRequired
 * @description Required-field keys from the catalog, plus i18n labels for save/completion copy.
 *
 * Responsibilities:
 * - Re-export REQUIRED_KEYS / RequiredKey from profileFields
 * - Map each required key to a profile message key
 *
 * This is the only profile rules file that imports i18n. A missing or extra
 * required field, or a typo'd message key, fails typecheck here.
 */

import type { MessageKey } from "@/i18n";
import { REQUIRED_KEYS, type RequiredKey } from "./profileFields";

export { REQUIRED_KEYS, type RequiredKey };

export const REQUIRED_LABELS: Record<RequiredKey, MessageKey<"profile">> = {
  name: "basic.name.label",
  identity: "basic.identity.label",
  job_direction: "jobIntent.direction.label",
  target_role: "jobIntent.role.label",
  self_intro: "skills.selfIntro.label",
  tech_domains: "skills.domains.label",
};
