"use client";

import { Sparkles } from "lucide-react";

export function TintIcon({ icon: Icon, tint }: { icon: typeof Sparkles; tint: string }) {
  const cls = {
    brand: "icon-badge icon-badge-brand",
    green: "icon-badge icon-badge-success",
    warning: "icon-badge icon-badge-warning",
    danger: "icon-badge icon-badge-danger",
  }[tint] ?? "icon-badge";
  return (
    <span className={cls}>
      <Icon size={16} strokeWidth={1.75} />
    </span>
  );
}
