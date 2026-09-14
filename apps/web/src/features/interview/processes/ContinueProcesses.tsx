"use client";

/** Recent passed processes with a "start next round" action (round 1 -> round 2 -> ...). */

import { useT, type Translator } from "@/i18n";
import { ArrowRight, GitBranch } from "lucide-react";
import type { InterviewProcessResponse } from "@/lib/api/contract";
import type { EligibleProcess } from "./eligibility";

export function roundLabel(t: Translator<"interview">, n: number) {
  return t("process.roundN", { n });
}

/** Realistic-chain label for one planned round (falls back to "Round N"). */
export function planStepLabel(
  t: Translator<"interview">,
  plan: InterviewProcessResponse["round_plan"],
  roundNo: number,
): string {
  const step = (plan ?? []).find((p) => p.round_no === roundNo);
  if (!step) return roundLabel(t, roundNo);
  const key = `process.kind.${step.kind}` as Parameters<Translator<"interview">>[0];
  return t(key);
}

export function ContinueProcessRow({
  process,
  starting,
  onStart,
}: {
  process: EligibleProcess;
  starting: boolean;
  onStart: () => void;
}) {
  const t = useT("interview");
  return (
    <div className="flex items-center justify-between gap-3 rounded-lg border border-[var(--border)] px-3 py-2">
      <div className="flex min-w-0 items-center gap-2 text-[13px]">
        <GitBranch size={14} className="shrink-0 text-ink-muted" strokeWidth={1.75} />
        <span className="truncate font-medium">{process.role}</span>
        <span className="shrink-0 text-ink-muted">·</span>
        <span className="shrink-0 text-ink-muted">{process.company}</span>
        <span className="chip chip-blue shrink-0">
          {planStepLabel(t, process.round_plan, process.current_round)}
        </span>
      </div>
      <button
        type="button"
        className="btn-secondary shrink-0 !px-2.5 !py-1 !text-xs"
        onClick={onStart}
        disabled={starting}
      >
        {starting ? (
          <span className="block h-3 w-3 anim-spin rounded-full border-2 border-current border-t-transparent" />
        ) : (
          <>
            {t("process.next", { n: process.next_round_no })}
            <ArrowRight size={12} className="btn-arrow transition-transform" />
          </>
        )}
      </button>
    </div>
  );
}

export function ContinueProcesses({
  processes,
  loading,
  startingId,
  onStart,
}: {
  processes: EligibleProcess[];
  loading: boolean;
  startingId: number | null;
  onStart: (process: EligibleProcess) => void;
}) {
  const t = useT("interview");
  if (loading && processes.length === 0) return null;
  if (processes.length === 0) return null;
  return (
    <section className="surface-card shrink-0 p-3.5">
      <div className="mb-2 flex items-center gap-2">
        <span className="icon-badge icon-badge-brand !h-7 !w-7">
          <GitBranch size={14} strokeWidth={1.75} />
        </span>
        <h2 className="text-[13px] font-semibold">{t("process.title")}</h2>
      </div>
      <div className="grid gap-1.5">
        {processes.map((p) => (
          <ContinueProcessRow
            key={p.id}
            process={p}
            starting={startingId === p.id}
            onStart={() => onStart(p)}
          />
        ))}
      </div>
    </section>
  );
}
