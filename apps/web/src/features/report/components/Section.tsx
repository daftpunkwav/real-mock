"use client";

/** Tone-tinted bullet list (brand/success/danger/warning) for report detail sections. */
export function Section({
  title,
  items,
  tone,
}: {
  title: string;
  items?: string[];
  tone: "brand" | "success" | "danger" | "warning";
}) {
  if (!items?.length) return null;
  const tintMap: Record<string, { bg: string; fg: string; border: string }> = {
    success: {
      bg: "var(--success-soft)",
      fg: "var(--success-ink)",
      border: "color-mix(in srgb, var(--success) 22%, transparent)",
    },
    danger: {
      bg: "var(--danger-soft)",
      fg: "var(--danger-ink)",
      border: "color-mix(in srgb, var(--danger) 22%, transparent)",
    },
    brand: {
      bg: "var(--info-soft)",
      fg: "var(--info-ink)",
      border: "color-mix(in srgb, var(--primary) 22%, transparent)",
    },
    warning: {
      bg: "var(--warning-soft)",
      fg: "var(--warning-ink)",
      border: "color-mix(in srgb, var(--warning) 28%, transparent)",
    },
  };
  const t = tintMap[tone] ?? tintMap.brand!;
  return (
    <div
      className="mt-4 rounded-md border p-4"
      style={{ background: t.bg, borderColor: t.border }}
    >
      <h3
        className="mb-2 text-[12px] font-semibold uppercase tracking-[0.08em]"
        style={{ color: t.fg }}
      >
        {title}
      </h3>
      <ul className="space-y-1.5">
        {items.map((item, i) => (
          <li key={i} className="flex items-start gap-2 text-[13px] leading-relaxed text-ink">
            <span className="mt-1 inline-block h-1 w-1 shrink-0 rounded-full bg-current opacity-50" />
            <span className="min-w-0 break-words">{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
