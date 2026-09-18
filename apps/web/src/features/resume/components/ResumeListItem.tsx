"use client";

/**
 * @file ResumeListItem.tsx
 * @description One resume family: version chips plus activate / delete / upload-version / analyze.
 *
 * Delete confirmation uses the shared ConfirmDialog and only removes this version.
 */

import { useRef, useState } from "react";
import { ChevronRight, FileText, Sparkles, Trash2, Upload } from "lucide-react";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Spinner } from "@/components/Spinner";
import { useT } from "@/i18n";
import { RESUME_ACCEPT } from "../resumeLimits";
import { canAddVersion, isLatestIdle, type ResumeFamilyGroup } from "../versionCompare";

interface ResumeListItemProps {
  group: ResumeFamilyGroup;
  previewId: number | null;
  analyzingIds: number[];
  uploading: boolean;
  onSelect: (id: number) => void;
  onActivate: (id: number) => void;
  onAnalyze: (id: number) => void;
  onDelete: (id: number) => void;
  onUploadVersion: (id: number, file: File) => void;
}

export function ResumeListItem({
  group,
  previewId,
  analyzingIds,
  uploading,
  onSelect,
  onActivate,
  onAnalyze,
  onDelete,
  onUploadVersion,
}: ResumeListItemProps) {
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const versionInputRef = useRef<HTMLInputElement>(null);
  const t = useT("resume");
  const latest = group.members[group.members.length - 1] ?? group.members[0];
  const selectedMember = group.members.find((row) => row.id === previewId);
  const r = selectedMember ?? latest;
  if (!r) return null;
  const selected = selectedMember != null;
  const analyzing = analyzingIds.includes(r.id);
  const atVersionCap = !canAddVersion(group.members.length);

  return (
    <li>
      <div
        role="button"
        tabIndex={0}
        onClick={() => onSelect(r.id)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") onSelect(r.id);
        }}
        className={`flex cursor-pointer items-center gap-3 px-4 py-3.5 ${
          selected ? "bg-[var(--info-soft)]" : "hover:bg-surface-alt"
        }`}
      >
        <span
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md ${
            selected
              ? "bg-[var(--primary)] text-white"
              : "bg-surface-alt text-ink-subtle"
          }`}
        >
          <FileText size={15} strokeWidth={1.75} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate text-[13px] font-medium text-ink">
              {r.filename}
            </span>
            {r.is_active && <span className="chip chip-blue">{t("item.chipActive")}</span>}
            {r.score != null && (
              <span className="chip chip-green">{t("item.scoreChip", { score: r.score })}</span>
            )}
          </div>
          <p className="mt-0.5 text-[11px] text-ink-subtle">
            {r.file_type.toUpperCase()}
            {r.parsed_profile.name ? ` · ${r.parsed_profile.name}` : ""}
          </p>
        </div>
        <ChevronRight
          size={15}
          className={`shrink-0 ${selected ? "text-[var(--primary)]" : "text-ink-subtle"}`}
        />
      </div>
      <div className={`flex flex-wrap gap-1 px-4 pb-3 ${selected ? "bg-[var(--info-soft)]" : ""}`}>
        {group.members.map((member) => (
          <button
            key={member.id}
            type="button"
            onClick={() => onSelect(member.id)}
            className={`chip ${member.id === r.id && selected ? "chip-blue" : "chip-gray"}`}
          >
            {t("item.versionChip", { n: member.version_n })}
            {isLatestIdle(group, member) ? ` · ${t("item.latestIdle")}` : ""}
          </button>
        ))}
      </div>

      {selected && (
        <div className="flex flex-wrap items-center gap-2 border-t border-surface-border bg-[var(--info-soft)] px-4 pb-3.5 pt-2">
          <button
            type="button"
            disabled={r.is_active}
            onClick={(e) => {
              e.stopPropagation();
              onActivate(r.id);
            }}
            className={`inline-flex h-8 items-center gap-1.5 rounded-md px-3 text-[12px] font-medium transition-colors ${
              r.is_active
                ? "bg-[var(--chip-blue-bg)] text-[var(--chip-blue-fg)]"
                : "border border-surface-border bg-surface-card text-ink-muted hover:border-[var(--primary)] hover:text-[var(--primary)]"
            }`}
          >
            {r.is_active ? t("item.currentActive") : t("item.setActive")}
          </button>
          <button
            type="button"
            disabled={uploading || atVersionCap}
            onClick={(e) => {
              e.stopPropagation();
              versionInputRef.current?.click();
            }}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-surface-border bg-surface-card px-3 text-[12px] font-medium text-ink-muted hover:border-[var(--primary)] hover:text-[var(--primary)] disabled:opacity-50"
          >
            <Upload size={12} />
            {t("item.uploadVersion")}
          </button>
          <input
            ref={versionInputRef}
            type="file"
            accept={RESUME_ACCEPT}
            className="hidden"
            onClick={(e) => e.stopPropagation()}
            onChange={(e) => {
              const file = e.target.files?.[0];
              e.target.value = "";
              if (file) onUploadVersion(r.id, file);
            }}
          />
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setConfirmingDelete(true);
            }}
            className="btn-danger ml-auto !h-8 !px-3 !text-xs"
          >
            <Trash2 size={12} />
            {t("item.delete")}
          </button>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onAnalyze(r.id);
            }}
            disabled={analyzing}
            className="btn-primary !h-8 !px-3 !text-xs"
          >
            {analyzing ? (
              <Spinner className="h-3 w-3" />
            ) : (
              <Sparkles size={12} />
            )}
            {analyzing ? t("item.analyzing") : t("item.analyze")}
          </button>
        </div>
      )}

      <ConfirmDialog
        open={confirmingDelete}
        title={t("item.deleteTitle")}
        message={t("item.deleteConfirm", { name: r.filename })}
        confirmLabel={t("item.delete")}
        onConfirm={() => {
          setConfirmingDelete(false);
          onDelete(r.id);
        }}
        onCancel={() => setConfirmingDelete(false)}
      />
    </li>
  );
}
