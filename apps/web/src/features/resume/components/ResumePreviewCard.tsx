"use client";

/**
 * @file ResumePreviewCard.tsx
 * @description Sticky original-file summary: name, score, skills, projects.
 *
 * Skill/project caps live in resumeLimits; chip shortening in resumePreview.
 */

import { CheckCircle, Eye, FileText, FolderOpen } from "lucide-react";
import { useT } from "@/i18n";
import type { Resume } from "../types";
import { buildResumePreviewUrl } from "../previewRoute";
import { PREVIEW_PROJECT_MAX, PREVIEW_SKILL_MAX } from "../resumeLimits";
import { shortSkillLabel } from "../resumePreview";

export function ResumePreviewCard({ resume: previewResume }: { resume: Resume | null }) {
  const t = useT("resume");
  return (
    <div className="surface-card p-4 sm:p-5">
      <h2 className="mb-3.5 flex items-center gap-2 text-[13px] font-semibold tracking-tight text-ink">
        <FolderOpen size={14} className="text-[var(--primary)]" />
        {t("previewCard.title")}
      </h2>
      {previewResume ? (
        <>
          <div className="mb-3 flex items-start gap-3">
            <span className="icon-badge icon-badge-brand shrink-0">
              <FileText size={16} strokeWidth={1.75} />
            </span>
            <div className="min-w-0">
              <p className="truncate text-[13px] font-semibold text-ink">{previewResume.filename}</p>
              <p className="mt-0.5 text-[11px] text-ink-subtle">
                {previewResume.parsed_profile.name || t("previewCard.nameUnknown")} ·{" "}
                {previewResume.file_type.toUpperCase()}
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => {
              if (!previewResume) return;
              window.open(
                buildResumePreviewUrl({
                  id: previewResume.id,
                  name: previewResume.filename,
                  type: previewResume.file_type,
                }),
                "_blank",
                "noopener,noreferrer",
              );
            }}
            className="btn-secondary mb-3 !h-8 w-full !text-[12px]"
          >
            <Eye size={13} />
            {t("previewCard.open")}
          </button>

          {previewResume.score != null && (
            <div className="mb-3">
              <div className="mb-1 flex justify-between text-[11px]">
                <span className="text-ink-subtle">{t("previewCard.score")}</span>
                <span className="font-mono font-semibold text-[var(--primary)] num-tabular">
                  {previewResume.score}
                </span>
              </div>
              <div className="progress">
                <div
                  className="progress-bar !bg-[var(--success)]"
                  style={{ width: `${Math.min(previewResume.score, 100)}%` }}
                />
              </div>
            </div>
          )}

          {previewResume.parsed_profile.summary && (
            <div className="mb-3">
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-subtle">
                {t("previewCard.summary")}
              </p>
              <p className="line-clamp-4 text-[12px] leading-relaxed text-ink-muted">
                {previewResume.parsed_profile.summary}
              </p>
            </div>
          )}

          {previewResume.parsed_profile.skills.length > 0 && (
            <div className="mb-3">
              <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-subtle">
                {t("previewCard.skills")}
              </p>
              <div className="flex flex-wrap gap-1">
                {previewResume.parsed_profile.skills.slice(0, PREVIEW_SKILL_MAX).map((s) => (
                  <span key={s} className="chip chip-blue !text-[10px]" title={s}>
                    {shortSkillLabel(s)}
                  </span>
                ))}
                {previewResume.parsed_profile.skills.length > PREVIEW_SKILL_MAX && (
                  <span className="chip chip-gray !text-[10px]">
                    +{previewResume.parsed_profile.skills.length - PREVIEW_SKILL_MAX}
                  </span>
                )}
              </div>
            </div>
          )}

          {previewResume.parsed_profile.projects.length > 0 && (
            <div>
              <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-ink-subtle">
                {t("previewCard.projects")}
              </p>
              <ul className="space-y-1.5">
                {previewResume.parsed_profile.projects.slice(0, PREVIEW_PROJECT_MAX).map((p, i) => (
                  <li key={i} className="flex items-start gap-1.5 text-[12px] text-ink-muted">
                    <CheckCircle size={11} className="mt-0.5 shrink-0 text-[var(--success)]" />
                    <span className="line-clamp-2">{p.name || p.description || t("previewCard.projectUnnamed")}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      ) : (
        <p className="py-4 text-center text-[13px] text-ink-subtle">{t("previewCard.empty")}</p>
      )}
    </div>
  );
}
