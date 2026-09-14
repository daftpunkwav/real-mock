"use client";

/** Multi-round process continuation: eligible-process helpers, continuation hook, and entry UI. */

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useT, type Translator } from "@/i18n";
import { getTranslator } from "@/i18n/resolve";
import { ArrowRight, GitBranch } from "lucide-react";
import { toast } from "@/components/Toast";
import { interviewHttp as api } from "@/lib/api/clients";
import type { InterviewProcessResponse } from "@/lib/api/contract";

/** A process whose latest round passed and with rounds remaining. */
export type EligibleProcess = InterviewProcessResponse & {
  next_round_no: number;
};

/** Pure helpers for multi-round process continuation (no React / no API). */
export function selectEligibleProcesses(
  processes: InterviewProcessResponse[],
): EligibleProcess[] {
  return processes
    .filter((p) => p.next_round_eligible && p.next_round_no != null)
    .map((p) => ({ ...p, next_round_no: p.next_round_no as number }))
    .sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""));
}

/** process_id → eligible next-round process (history detail actions). */
export function buildNextRoundIndex(
  processes: EligibleProcess[],
): Record<number, EligibleProcess> {
  const index: Record<number, EligibleProcess> = {};
  for (const p of processes) index[p.id] = p;
  return index;
}

/** Continue-process data domain: eligible multi-round processes + next-round creation. */
export function useProcessContinuation() {
  const router = useRouter();
  const [processes, setProcesses] = useState<EligibleProcess[]>([]);
  const [loading, setLoading] = useState(true);
  const [startingId, setStartingId] = useState<number | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    api
      .listProcesses()
      .then((rows) => setProcesses(selectEligibleProcesses(rows)))
      .catch(() => setProcesses([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const startNext = async (process: EligibleProcess) => {
    const t = getTranslator("interview");
    setStartingId(process.id);
    try {
      const session = await api.createNextRound(process.id);
      router.push(`/interview/${session.id}`);
    } catch (e) {
      toast.error(
        e instanceof Error ? e.message : t("process.nextFailed"),
      );
      setStartingId(null);
    }
  };

  return { processes, loading, startingId, startNext, reload: load };
}

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

/** Hover detail for one planned round: focus + HR pass bar (empty when none). */
export function planStepTitle(
  plan: InterviewProcessResponse["round_plan"],
  roundNo: number,
): string {
  const step = (plan ?? []).find((p) => p.round_no === roundNo);
  if (!step) return "";
  const pass = step.pass_criteria?.trim() ? `\n${step.pass_criteria.trim()}` : "";
  return `${step.focus}${pass}`.trim();
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
        <span className="chip chip-blue shrink-0" title={planStepTitle(process.round_plan, process.current_round) || undefined}>
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

/** Recent passed processes with a "start next round" action (round 1 -> round 2 -> ...). */
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
