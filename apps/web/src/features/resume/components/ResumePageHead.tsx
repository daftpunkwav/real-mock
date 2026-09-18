"use client";

/**
 * @file ResumePageHead.tsx
 * @description Resume page title block with icon badge and eyebrow.
 */

import { FileText } from "lucide-react";
import { useT } from "@/i18n";

/** Resume page title block (eyebrow + title). */
export function ResumePageHead() {
  const t = useT("resume");
  return (
    <div className="page-header">
      <div className="flex items-start gap-3">
        <span className="icon-badge icon-badge-brand">
          <FileText size={18} strokeWidth={1.75} />
        </span>
        <div>
          <p className="page-eyebrow">{t("head.eyebrow")}</p>
          <h1 className="page-title">{t("head.title")}</h1>
        </div>
      </div>
    </div>
  );
}
