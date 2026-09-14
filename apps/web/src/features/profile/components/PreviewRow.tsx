"use client";

/**
 * @file PreviewRow.tsx
 * @description Icon + label + value row used inside the profile preview card.
 *
 * Responsibilities:
 * - Render a compact definition-list style preview line
 * - Accept a lucide-style icon component for visual hierarchy
 */

import type { ComponentType } from "react";

export function PreviewRow({
  icon: Icon,
  label,
  value,
}: {
  icon: ComponentType<{ size?: number; className?: string; strokeWidth?: number }>;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-start gap-3">
      <Icon size={14} className="mt-1 shrink-0 text-ink-subtle" strokeWidth={1.75} />
      <div className="min-w-0 flex-1">
        <dt className="text-[10px] uppercase leading-none tracking-[0.1em] text-ink-subtle">
          {label}
        </dt>
        <dd className="mt-1.5 break-words text-[13px] font-medium leading-snug text-ink">
          {value}
        </dd>
      </div>
    </div>
  );
}
