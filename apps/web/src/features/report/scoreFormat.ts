import type { ScoreBreakdown } from "@/types";

/** Nullable rounded scores; null renders as an em dash. */
export interface NormalizedScores {
  technical: number | null;
  communication: number | null;
  project_depth: number | null;
  problem_solving: number | null;
  presence: number | null;
  politeness: number | null;
  overall: number | null;
}

/** Round finite scores; keep null for missing values. */
export function normalizeScores(raw: ScoreBreakdown | undefined | null): NormalizedScores {
  const pick = (v: unknown): number | null =>
    typeof v === "number" && Number.isFinite(v) ? Math.round(v) : null;
  return {
    technical: pick(raw?.technical),
    communication: pick(raw?.communication),
    project_depth: pick(raw?.project_depth),
    problem_solving: pick(raw?.problem_solving),
    presence: pick(raw?.presence),
    politeness: pick(raw?.politeness),
    overall: pick(raw?.overall),
  };
}

export function formatScore(score: number | null | undefined): string {
  if (typeof score !== "number" || !Number.isFinite(score)) return "—";
  return String(Math.round(score));
}
