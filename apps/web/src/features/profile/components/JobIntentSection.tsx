"use client";

/**
 * @file JobIntentSection.tsx
 * @description Collapsible section for job-seeking intent and preference fields.
 *
 * Responsibilities:
 * - Edit direction, target role, experience, location, salary, and related prefs
 * - Mark job_direction and target_role as required with validation errors
 */

import { Briefcase } from "lucide-react";
import { CollapsibleSection } from "@/components/CollapsibleSection";
import { useT } from "@/i18n";
import { PROFILE_FIELD_LIMITS } from "../profileLimits";
import { Field } from "./Field";
import type { ProfileSectionProps } from "../types";

export function JobIntentSection({ profile, patch, requiredError }: ProfileSectionProps) {
  const t = useT("profile");
  return (
    <CollapsibleSection title={t("jobIntent.title")} icon={Briefcase} tone="brand">
      <div className="grid grid-cols-1 gap-x-4 gap-y-4 sm:grid-cols-2">
        <Field
          label={t("jobIntent.direction.label")}
          required
          error={requiredError("job_direction")}
          value={profile.job_direction}
          maxLength={PROFILE_FIELD_LIMITS.job_direction}
          onChange={(v) => patch("job_direction", v)}
        />
        <Field
          label={t("jobIntent.role.label")}
          required
          error={requiredError("target_role")}
          value={profile.target_role}
          maxLength={PROFILE_FIELD_LIMITS.target_role}
          onChange={(v) => patch("target_role", v)}
        />
        <Field
          label={t("jobIntent.experience.label")}
          value={profile.experience_years}
          maxLength={PROFILE_FIELD_LIMITS.experience_years}
          onChange={(v) => patch("experience_years", v)}
        />
        <Field
          label={t("jobIntent.experienceDetail.label")}
          value={profile.work_years_detail || ""}
          maxLength={PROFILE_FIELD_LIMITS.work_years_detail}
          onChange={(v) => patch("work_years_detail", v)}
        />
        <Field
          label={t("jobIntent.company.label")}
          value={profile.current_company || ""}
          maxLength={PROFILE_FIELD_LIMITS.current_company}
          onChange={(v) => patch("current_company", v)}
        />
        <Field
          label={t("jobIntent.salary.label")}
          value={profile.expected_salary || ""}
          maxLength={PROFILE_FIELD_LIMITS.expected_salary}
          onChange={(v) => patch("expected_salary", v)}
        />
        <Field
          label={t("jobIntent.city.label")}
          value={profile.city || ""}
          maxLength={PROFILE_FIELD_LIMITS.city}
          onChange={(v) => patch("city", v)}
        />
        <Field
          label={t("jobIntent.expectedCity.label")}
          value={profile.expected_city || ""}
          maxLength={PROFILE_FIELD_LIMITS.expected_city}
          onChange={(v) => patch("expected_city", v)}
        />
        <Field
          label={t("jobIntent.noticePeriod.label")}
          value={profile.notice_period || ""}
          maxLength={PROFILE_FIELD_LIMITS.notice_period}
          onChange={(v) => patch("notice_period", v)}
        />
        <Field
          label={t("jobIntent.remote.label")}
          value={profile.open_to_remote || ""}
          maxLength={PROFILE_FIELD_LIMITS.open_to_remote}
          onChange={(v) => patch("open_to_remote", v)}
        />
      </div>
    </CollapsibleSection>
  );
}
