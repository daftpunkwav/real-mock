"use client";

import type { ReactNode } from "react";

/** Room page full screen Gate: Universal display of three entrances: invalid ID/missing token/failed connection. */
export function InterviewRoomGate({
  icon,
  title,
  desc,
  tone,
  onPrimary,
  primaryLabel,
  onSecondary,
  secondaryLabel,
}: {
  icon: ReactNode;
  title: string;
  desc: string;
  tone: "warning" | "danger";
  onPrimary: () => void;
  primaryLabel: string;
  onSecondary?: () => void;
  secondaryLabel?: string;
}) {
  const iconClass =
    tone === "danger"
      ? "!bg-[var(--danger-soft)] !text-[var(--danger-ink)]"
      : "!bg-[var(--warning-soft)] !text-[var(--warning-ink)]";
  return (
    <div className="h-screen flex flex-col items-center justify-center gap-4 bg-[var(--background)] px-6 text-center">
      <span className={`empty-state-icon ${iconClass}`}>{icon}</span>
      <div>
        <p className="text-[16px] font-medium text-ink">{title}</p>
        <p className="mt-1.5 max-w-sm text-[13px] text-ink-muted">{desc}</p>
      </div>
      <div className="mt-1 flex flex-wrap items-center justify-center gap-2.5">
        <button type="button" onClick={onPrimary} className="btn-primary">
          {primaryLabel}
        </button>
        {onSecondary && secondaryLabel ? (
          <button type="button" onClick={onSecondary} className="btn-secondary">
            {secondaryLabel}
          </button>
        ) : null}
      </div>
    </div>
  );
}
