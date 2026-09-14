"use client";

/**
 * @file PreviewCard.tsx
 * @description Live profile preview card summarizing key fields and tech domains.
 *
 * Responsibilities:
 * - Show avatar initial, or a generic icon when name is empty (never a fake "?")
 * - Render PreviewRow entries only for filled fields
 * - List filled tech domains and a clamped self-intro snippet
 */

import {
  Award,
  Briefcase,
  Building2,
  GraduationCap,
  Link2,
  Mail,
  MapPin,
  Phone,
  User,
} from "lucide-react";
import type { UserProfileResponse as UserProfile } from "@/lib/api/contract";
import { useT } from "@/i18n";
import { avatarInitial, isPreviewFilled } from "../previewIdentity";
import { PreviewRow } from "./PreviewRow";

export function PreviewCard({
  profile,
  filledDomains,
}: {
  profile: UserProfile;
  filledDomains: string[];
}) {
  const t = useT("profile");
  const name = profile.name.trim();
  const initial = avatarInitial(profile.name);
  return (
    <div className="surface-card p-5">
      <div className="mb-5 flex items-center gap-3.5">
        <div
          className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full text-lg font-semibold tracking-tight text-white"
          style={{ background: "var(--primary)" }}
          aria-hidden
        >
          {initial ? initial : <User size={20} strokeWidth={1.75} />}
        </div>
        <div className="min-w-0">
          <h2 className="truncate text-[15px] font-semibold leading-snug tracking-tight text-ink">
            {name || t("preview.unnamed")}
          </h2>
          <p className="mt-1 truncate text-[11px] text-ink-subtle">
            {[profile.identity, profile.school]
              .map((part) => part.trim())
              .filter(Boolean)
              .join(" · ") || t("preview.emptyHint")}
          </p>
        </div>
      </div>

      <dl className="space-y-3.5">
        {isPreviewFilled(profile.major) && (
          <PreviewRow
            icon={GraduationCap}
            label={t("preview.major.label")}
            value={
              isPreviewFilled(profile.graduation_year)
                ? t("preview.major.value", { major: profile.major, year: profile.graduation_year })
                : profile.major
            }
          />
        )}
        {isPreviewFilled(profile.education_level) && (
          <PreviewRow icon={Award} label={t("preview.degree.label")} value={profile.education_level} />
        )}
        {isPreviewFilled(profile.target_role) && (
          <PreviewRow icon={Briefcase} label={t("preview.role.label")} value={profile.target_role} />
        )}
        {isPreviewFilled(profile.job_direction) && (
          <PreviewRow icon={MapPin} label={t("preview.direction.label")} value={profile.job_direction} />
        )}
        {isPreviewFilled(profile.current_company) && (
          <PreviewRow icon={Building2} label={t("preview.company.label")} value={profile.current_company} />
        )}
        {isPreviewFilled(profile.expected_city) && (
          <PreviewRow icon={MapPin} label={t("preview.expectedCity.label")} value={profile.expected_city} />
        )}
        {isPreviewFilled(profile.city) && !isPreviewFilled(profile.expected_city) && (
          <PreviewRow icon={MapPin} label={t("preview.city.label")} value={profile.city} />
        )}
        {isPreviewFilled(profile.email) && (
          <PreviewRow icon={Mail} label={t("preview.email.label")} value={profile.email} />
        )}
        {isPreviewFilled(profile.phone) && (
          <PreviewRow icon={Phone} label={t("preview.phone.label")} value={profile.phone} />
        )}
        {isPreviewFilled(profile.github_username) && (
          <PreviewRow icon={Link2} label={t("preview.github.label")} value={profile.github_username} />
        )}
      </dl>

      {filledDomains.length > 0 && (
        <div className="mt-5 border-t border-surface-border pt-4">
          <p className="mb-2.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-subtle">
            {t("preview.domains.title")}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {filledDomains.map((d, i) => (
              <span key={`${d}-${i}`} className="chip chip-blue">
                {d}
              </span>
            ))}
          </div>
        </div>
      )}

      {isPreviewFilled(profile.self_intro) && (
        <div className="mt-5 border-t border-surface-border pt-4">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-subtle">
            {t("preview.selfIntro.title")}
          </p>
          <p className="line-clamp-6 text-[12.5px] leading-relaxed text-ink-muted text-balance">
            {profile.self_intro}
          </p>
        </div>
      )}
    </div>
  );
}
