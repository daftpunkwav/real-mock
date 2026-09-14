"use client";

/** Round verdict banner: passed (green) / failed (red) + the agent's reasoning. */

import { useT } from "@/i18n";
import { CheckCircle2, XCircle } from "lucide-react";

export function VerdictBanner({
  verdict,
  reasoning,
}: {
  verdict?: string | null;
  reasoning?: string;
}) {
  const t = useT("report");
  if (verdict !== "passed" && verdict !== "failed") return null;
  const passed = verdict === "passed";
  const Icon = passed ? CheckCircle2 : XCircle;
  return (
    <div
      className="mt-4 flex items-start gap-3 rounded-md border p-4"
      style={{
        background: passed ? "var(--success-soft)" : "var(--danger-soft)",
        borderColor: passed
          ? "color-mix(in srgb, var(--success) 22%, transparent)"
          : "color-mix(in srgb, var(--danger) 22%, transparent)",
      }}
    >
      <Icon
        size={20}
        strokeWidth={1.75}
        className="mt-0.5 shrink-0"
        style={{ color: passed ? "var(--success-ink)" : "var(--danger-ink)" }}
      />
      <div className="min-w-0">
        <p
          className="text-[15px] font-semibold"
          style={{ color: passed ? "var(--success-ink)" : "var(--danger-ink)" }}
        >
          {passed ? t("verdict.passed") : t("verdict.failed")}
        </p>
        {reasoning && (
          <p className="mt-1 text-[13px] leading-relaxed text-ink">{reasoning}</p>
        )}
      </div>
    </div>
  );
}
