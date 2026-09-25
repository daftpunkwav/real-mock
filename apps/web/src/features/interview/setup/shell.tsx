"use client";

/** Interview setup chrome: header row with the start action, loading state, and the setup grid. */

import { useT } from "@/i18n";
import { Sparkles } from "lucide-react";
import type { ReactNode } from "react";
import { PageSkeleton } from "@/components/loading/PageSkeleton";

export function SetupHeader({ action }: { action?: ReactNode }) {
  const t = useT("interview");
  return (
    <div className="mb-4 flex shrink-0 items-center justify-between gap-4">
      <div className="page-header !mb-0 min-w-0">
        <div className="flex items-start gap-3">
          <span className="icon-badge icon-badge-brand shrink-0">
            <Sparkles size={18} strokeWidth={1.75} />
          </span>
          <div className="min-w-0">
            <p className="page-eyebrow">{t("setup.eyebrow")}</p>
            <h1 className="page-title">{t("setup.title")}</h1>
          </div>
        </div>
      </div>
      {action ? <div className="hidden sm:block">{action}</div> : null}
    </div>
  );
}

export function SetupLoading() {
  // Real header stays above; the body shimmers as setup cards load.
  return <PageSkeleton variant="board" header={false} shell={false} />;
}

export function SetupMain({ left, preview }: { left: ReactNode; preview: ReactNode }) {
  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 overflow-hidden lg:grid-cols-[1fr_260px]">
      {left}
      <div className="hidden min-h-0 flex-col gap-2.5 overflow-hidden lg:flex">{preview}</div>
    </div>
  );
}
