"use client";

/**
 * @file SkillsSection.tsx
 * @description Collapsible section for narrative skills fields and tech domain chips.
 *
 * Responsibilities:
 * - Edit self-intro, highlights, projects, strengths/weaknesses, and certificates
 * - Manage add/remove of tech domain tags with focus on newly added inputs
 * - Enforce item/count limits and required validation for self_intro and tech_domains
 */

import { useEffect, useRef } from "react";
import { Plus, Sparkles, X } from "lucide-react";
import { CollapsibleSection } from "@/components/CollapsibleSection";
import { useT } from "@/i18n";
import { PROFILE_FIELD_LIMITS, TECH_DOMAIN_ITEM_MAX, TECH_DOMAINS_MAX_COUNT } from "../profileLimits";
import type { ProfileSectionProps } from "../types";
import { LimitedTextarea } from "./LimitedTextarea";

export function SkillsSection({
  profile,
  patch,
  requiredError,
  onAddDomain,
  onRemoveDomain,
}: ProfileSectionProps & {
  onAddDomain: () => void;
  onRemoveDomain: (i: number) => void;
}) {
  const t = useT("profile");
  const lastInputRef = useRef<HTMLInputElement | null>(null);
  const prevCountRef = useRef(profile.tech_domains.length);

  // Focus the last input only when domain count increases (not on delete/clear)
  useEffect(() => {
    if (profile.tech_domains.length > prevCountRef.current) {
      lastInputRef.current?.focus();
    }
    prevCountRef.current = profile.tech_domains.length;
  }, [profile.tech_domains.length]);

  return (
    <CollapsibleSection title={t("skills.title")} icon={Sparkles} tone="brand">
      <div className="space-y-4">
        <LimitedTextarea
          label={t("skills.selfIntro.label")}
          required
          error={requiredError("self_intro")}
          value={profile.self_intro || ""}
          onChange={(v) => patch("self_intro", v)}
          limit={PROFILE_FIELD_LIMITS.self_intro}
          rows={4}
        />
        <LimitedTextarea
          label={t("skills.highlights.label")}
          value={profile.career_highlights || ""}
          onChange={(v) => patch("career_highlights", v)}
          limit={PROFILE_FIELD_LIMITS.career_highlights}
          rows={3}
        />
        <LimitedTextarea
          label={t("skills.projects.label")}
          value={profile.signature_projects || ""}
          onChange={(v) => patch("signature_projects", v)}
          limit={PROFILE_FIELD_LIMITS.signature_projects}
          rows={3}
        />
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <LimitedTextarea
            label={t("skills.strengths.label")}
            value={profile.strengths || ""}
            onChange={(v) => patch("strengths", v)}
            limit={PROFILE_FIELD_LIMITS.strengths}
            rows={3}
          />
          <LimitedTextarea
            label={t("skills.weaknesses.label")}
            value={profile.weaknesses || ""}
            onChange={(v) => patch("weaknesses", v)}
            limit={PROFILE_FIELD_LIMITS.weaknesses}
            rows={3}
          />
        </div>
        <LimitedTextarea
          label={t("skills.certificates.label")}
          value={profile.certificates || ""}
          onChange={(v) => patch("certificates", v)}
          limit={PROFILE_FIELD_LIMITS.certificates}
          rows={2}
        />
        <div>
          <div className="mb-2 flex items-center justify-between">
            <label className="field-label !mb-0">
              {t("skills.domains.label")} <span className="text-[var(--danger)]">*</span>
            </label>
            <button
              type="button"
              onClick={onAddDomain}
              disabled={profile.tech_domains.length >= TECH_DOMAINS_MAX_COUNT}
              className="btn-tertiary !h-8 !px-2 !text-xs text-[var(--primary)] disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Plus size={13} /> {t("skills.domains.add")}
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            {profile.tech_domains.map((d, i) => (
              <div
                key={i}
                className={`inline-flex h-9 items-center gap-1 rounded-md border bg-surface-card pl-3 pr-1 transition-colors focus-within:border-[var(--primary)] focus-within:shadow-focus ${
                  requiredError("tech_domains") ? "border-[var(--danger)]" : "border-surface-border"
                }`}
              >
                <input
                  ref={i === profile.tech_domains.length - 1 ? lastInputRef : undefined}
                  className="w-28 bg-transparent text-[13px] outline-none sm:w-32"
                  value={d}
                  maxLength={TECH_DOMAIN_ITEM_MAX}
                  onChange={(e) => {
                    const domains = [...profile.tech_domains];
                    domains[i] = e.target.value;
                    patch("tech_domains", domains);
                  }}
                />
                <button
                  type="button"
                  onClick={() => onRemoveDomain(i)}
                  className="flex h-7 w-7 items-center justify-center rounded-full text-ink-muted transition-colors hover:bg-surface-muted hover:text-ink"
                  aria-label={t("skills.domains.remove")}
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
          {requiredError("tech_domains") && (
            <p className="field-error">{t("skills.domains.error")}</p>
          )}
        </div>
      </div>
    </CollapsibleSection>
  );
}
