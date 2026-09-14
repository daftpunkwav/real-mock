"use client";

import type { ComponentType, ReactNode } from "react";

type IconType = ComponentType<{ size?: number; className?: string; strokeWidth?: number }>;

/** Growth page section card: title + icon + children (different from the report page Section responsibilities and maintained independently). */
export function Section({
  title,
  icon: Icon,
  children,
}: {
  title: string;
  icon: IconType;
  children: ReactNode;
}) {
  return (
    <section className="surface-card overflow-hidden">
      <header className="flex items-center gap-2.5 border-b border-surface-border bg-surface-alt px-5 py-3.5">
        <span className="icon-badge icon-badge-brand">
          <Icon size={15} strokeWidth={1.75} />
        </span>
        <h2 className="text-[14px] font-semibold tracking-tight text-ink">{title}</h2>
      </header>
      <div className="p-5">{children}</div>
    </section>
  );
}
