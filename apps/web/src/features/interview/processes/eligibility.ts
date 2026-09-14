/** Pure helpers for multi-round process continuation (no React / no API). */

import type { InterviewProcessResponse } from "@/lib/api/contract";

/** A process whose latest round passed and with rounds remaining. */
export type EligibleProcess = InterviewProcessResponse & {
  next_round_no: number;
};

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
