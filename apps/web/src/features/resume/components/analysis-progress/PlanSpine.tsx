"use client";

/**
 * @file PlanSpine
 * @description Vertical plan-step spine for the live review desk.
 */

import { Check } from "lucide-react";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";
import type { ReviewPlanStep } from "../../reviewProgress";

function statusOf(step: ReviewPlanStep): string {
  return String(step.status || "pending");
}

export function PlanSpine({ steps }: { steps: ReviewPlanStep[] }) {
  const t = useT("resume");
  if (steps.length === 0) {
    return <p className="text-[12px] leading-relaxed text-ink-subtle">{t("stage.waiting")}</p>;
  }
  return (
    <ol className="relative m-0 list-none p-0">
      <span
        aria-hidden
        className="absolute bottom-2 left-[7px] top-2 w-px bg-surface-border"
      />
      {steps.map((step, index) => {
        const status = statusOf(step);
        const done = status === "done" || status === "skipped";
        const active = status === "in_progress";
        const parallel = step.mode === "parallel";
        return (
          <li key={step.id || `${step.title}-${index}`} className="relative flex items-start gap-2.5 pb-3 last:pb-0">
            <span
              className={cn(
                "relative z-[1] mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border bg-[var(--card)]",
                done && "border-[var(--success)] bg-[var(--success)] text-white",
                active && "border-[var(--primary)]",
                !done && !active && "border-surface-border",
              )}
            >
              {done ? (
                <Check size={10} strokeWidth={3} />
              ) : active ? (
                <span className="h-1.5 w-1.5 motion-safe:animate-pulse rounded-full bg-[var(--primary)]" />
              ) : null}
            </span>
            <span
              className={cn(
                "min-w-0 pt-px text-[12px] leading-snug",
                active ? "font-medium text-ink" : done ? "text-ink-subtle" : "text-ink-subtle/55",
              )}
            >
              <span className="flex flex-wrap items-center gap-1.5">
                <span className="min-w-0 break-words">{step.title}</span>
                {parallel ? (
                  <span className="chip shrink-0 !text-[10px]" title={t("stage.parallelHint")}>
                    {t("stage.parallel")}
                  </span>
                ) : null}
              </span>
              {step.note ? (
                <span className="mt-0.5 block text-[11px] font-normal text-ink-subtle">{step.note}</span>
              ) : null}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
