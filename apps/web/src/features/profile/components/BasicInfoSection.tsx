"use client";

/**
 * @file BasicInfoSection.tsx
 * @description Collapsible section for basic personal contact fields.
 *
 * Responsibilities:
 * - Edit name, gender, identity, email, and phone/WeChat
 * - Enforce field limits and required validation for name and identity
 */

import { User } from "lucide-react";
import { CollapsibleSection } from "@/components/CollapsibleSection";
import { useT } from "@/i18n";
import { PROFILE_FIELD_LIMITS } from "../profileLimits";
import { Field } from "./Field";
import type { ProfileSectionProps } from "../types";

export function BasicInfoSection({ profile, patch, requiredError }: ProfileSectionProps) {
  const t = useT("profile");
  return (
    <CollapsibleSection title={t("basic.title")} icon={User} tone="brand">
      <div className="grid grid-cols-1 gap-x-4 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
        <Field
          label={t("basic.name.label")}
          required
          error={requiredError("name")}
          value={profile.name}
          maxLength={PROFILE_FIELD_LIMITS.name}
          onChange={(v) => patch("name", v)}
        />
        <Field
          label={t("basic.gender.label")}
          value={profile.gender || ""}
          maxLength={PROFILE_FIELD_LIMITS.gender}
          onChange={(v) => patch("gender", v)}
        />
        <Field
          label={t("basic.identity.label")}
          required
          error={requiredError("identity")}
          value={profile.identity || ""}
          maxLength={PROFILE_FIELD_LIMITS.identity}
          onChange={(v) => patch("identity", v)}
        />
        <Field
          label={t("basic.email.label")}
          value={profile.email || ""}
          maxLength={PROFILE_FIELD_LIMITS.email}
          onChange={(v) => patch("email", v)}
        />
        <Field
          label={t("basic.phone.label")}
          value={profile.phone || ""}
          maxLength={PROFILE_FIELD_LIMITS.phone}
          onChange={(v) => patch("phone", v)}
        />
      </div>
    </CollapsibleSection>
  );
}
