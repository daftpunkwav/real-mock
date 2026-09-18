"use client";

/**
 * @file PageHead.tsx
 * @description Profile page title block with icon badge and eyebrow.
 *
 * Responsibilities:
 * - Present the page eyebrow and title consistently across load states
 */

import { User } from "lucide-react";
import { useT } from "@/i18n";

export function PageHead() {
  const t = useT("profile");
  return (
    <div className="flex items-start gap-3">
      <span className="icon-badge icon-badge-brand">
        <User size={18} strokeWidth={1.75} />
      </span>
      <div>
        <p className="page-eyebrow">{t("page.eyebrow")}</p>
        <h1 className="page-title">{t("page.title")}</h1>
      </div>
    </div>
  );
}
