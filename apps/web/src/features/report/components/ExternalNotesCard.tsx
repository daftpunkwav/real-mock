"use client";

// External verification notes surfaced by the report synthesis agent.
// Pure display component: receives pre-rendered note strings from the report page.

import { Globe } from "lucide-react";
import { useT } from "@/i18n";

/** External verification notes the report agent grounded via web tools. */
export function ExternalNotesCard({ notes }: { notes?: string[] }) {
  const t = useT("report");
  if (!notes?.length) return null;
  return (
    <div
      className="mt-4 rounded-md border p-4"
      style={{
        background: "var(--info-soft)",
        borderColor: "color-mix(in srgb, var(--primary) 22%, transparent)",
      }}
    >
      <h3
        className="mb-2 flex items-center gap-1.5 text-[12px] font-semibold uppercase tracking-[0.08em]"
        style={{ color: "var(--info-ink)" }}
      >
        <Globe size={12} />
        {t("sections.externalNotes")}
      </h3>
      <ul className="space-y-1.5">
        {notes.map((note, i) => (
          <li key={i} className="flex items-start gap-2 text-[13px] leading-relaxed text-ink">
            <span className="mt-1 inline-block h-1 w-1 shrink-0 rounded-full bg-current opacity-50" />
            <span className="min-w-0 break-words">{note}</span>
          </li>
        ))}
      </ul>
      <p className="mt-2 text-[11px]" style={{ color: "var(--info-ink)" }}>
        {t("externalNotes.hint")}
      </p>
    </div>
  );
}
