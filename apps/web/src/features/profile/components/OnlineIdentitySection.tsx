"use client";

/**
 * @file OnlineIdentitySection.tsx
 * @description Collapsible section for online presence and portfolio links.
 *
 * Responsibilities:
 * - Edit GitHub, preferred languages, portfolio/blog, and LinkedIn URLs
 * - Enforce profile field maxLength limits
 */

import { Link2 } from "lucide-react";
import { CollapsibleSection } from "@/components/CollapsibleSection";
import { useT } from "@/i18n";
import { PROFILE_FIELD_LIMITS } from "../profileLimits";
import { Field } from "./Field";
import type { ProfileSectionProps } from "../types";

export function OnlineIdentitySection({ profile, patch }: ProfileSectionProps) {
  const t = useT("profile");
  return (
    <CollapsibleSection title={t("online.title")} icon={Link2} tone="brand">
      <div className="grid grid-cols-1 gap-x-4 gap-y-4 sm:grid-cols-2">
        <Field
          label={t("online.github.label")}
          value={profile.github_username || ""}
          maxLength={PROFILE_FIELD_LIMITS.github_username}
          onChange={(v) => patch("github_username", v)}
        />
        <Field
          label={t("online.languages.label")}
          value={profile.preferred_languages || ""}
          maxLength={PROFILE_FIELD_LIMITS.preferred_languages}
          onChange={(v) => patch("preferred_languages", v)}
        />
        <Field
          label={t("online.portfolio.label")}
          value={profile.portfolio_url || ""}
          maxLength={PROFILE_FIELD_LIMITS.portfolio_url}
          onChange={(v) => patch("portfolio_url", v)}
          className="sm:col-span-2"
        />
        <Field
          label={t("online.linkedin.label")}
          value={profile.linkedin_url || ""}
          maxLength={PROFILE_FIELD_LIMITS.linkedin_url}
          onChange={(v) => patch("linkedin_url", v)}
          className="sm:col-span-2"
        />
      </div>
    </CollapsibleSection>
  );
}
