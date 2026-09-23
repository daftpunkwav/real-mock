"use client";

/**
 * @file ResumeList.tsx
 * @description Resume list card: count, empty state, and family groups.
 */

import { FileText } from "lucide-react";
import type { Resume } from "../types";
import { useT } from "@/i18n";
import { groupResumeFamilies } from "../versionCompare";
import { ResumeListItem } from "./ResumeListItem";

interface ResumeListProps {
  resumes: Resume[];
  previewId: number | null;
  analyzingIds: number[];
  uploading: boolean;
  onSelect: (id: number) => void;
  onActivate: (id: number) => void;
  onAnalyze: (id: number) => void;
  onDelete: (id: number) => void;
  onUploadVersion: (id: number, file: File) => void;
  onRetryParse: (id: number) => void;
}

export function ResumeList({
  resumes,
  previewId,
  analyzingIds,
  uploading,
  onSelect,
  onActivate,
  onAnalyze,
  onDelete,
  onUploadVersion,
  onRetryParse,
}: ResumeListProps) {
  const t = useT("resume");
  const groups = groupResumeFamilies(resumes);
  return (
    <div className="surface-card overflow-hidden">
      <div className="flex items-center justify-between border-b border-surface-border px-4 py-3">
        <h2 className="text-[13px] font-semibold tracking-tight text-ink">{t("list.title")}</h2>
        <span className="chip chip-gray">{t("list.count", { count: resumes.length })}</span>
      </div>

      {resumes.length === 0 ? (
        <div className="empty-state !py-12">
          <div className="empty-state-icon">
            <FileText size={22} />
          </div>
          <p className="text-[13px]">{t("list.empty")}</p>
        </div>
      ) : (
        <ul className="divide-y divide-surface-border">
          {groups.map((group) => (
            <ResumeListItem
              key={group.familyId}
              group={group}
              previewId={previewId}
              analyzingIds={analyzingIds}
              uploading={uploading}
              onSelect={onSelect}
              onActivate={onActivate}
              onAnalyze={onAnalyze}
              onDelete={onDelete}
              onUploadVersion={onUploadVersion}
              onRetryParse={onRetryParse}
            />
          ))}
        </ul>
      )}
    </div>
  );
}
