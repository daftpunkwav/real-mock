"use client";

/**
 * @file EducationSection.tsx
 * @description Collapsible section for education background fields.
 *
 * Responsibilities:
 * - Edit school, major, education level, graduation year, and English level
 * - Enforce profile field maxLength limits
 */

import { GraduationCap } from "lucide-react";
import { CollapsibleSection } from "@/components/CollapsibleSection";
import { useT } from "@/i18n";
import { PROFILE_FIELD_LIMITS } from "../profileLimits";
import { Field } from "./Field";
import type { ProfileSectionProps } from "../types";

export function EducationSection({ profile, patch }: ProfileSectionProps) {
  const t = useT("profile");
  return (
    <CollapsibleSection title={t("education.title")} icon={GraduationCap} tone="brand">
      <div className="grid grid-cols-1 gap-x-4 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
        <Field
          label={t("education.school.label")}
          value={profile.school || ""}
          maxLength={PROFILE_FIELD_LIMITS.school}
          onChange={(v) => patch("school", v)}
        />
        <Field
          label={t("education.major.label")}
          value={profile.major || ""}
          maxLength={PROFILE_FIELD_LIMITS.major}
          onChange={(v) => patch("major", v)}
        />
        <Field
          label={t("education.level.label")}
          value={profile.education_level || ""}
          maxLength={PROFILE_FIELD_LIMITS.education_level}
          onChange={(v) => patch("education_level", v)}
        />
        <Field
          label={t("education.graduationYear.label")}
          value={profile.graduation_year || ""}
          maxLength={PROFILE_FIELD_LIMITS.graduation_year}
          onChange={(v) => patch("graduation_year", v)}
        />
        <Field
          label={t("education.english.label")}
          value={profile.english_level || ""}
          maxLength={PROFILE_FIELD_LIMITS.english_level}
          onChange={(v) => patch("english_level", v)}
        />
      </div>
    </CollapsibleSection>
  );
}
