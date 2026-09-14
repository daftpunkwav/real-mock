import type { GrowthRecord } from "@/types";
import { getTranslator } from "@/i18n/resolve";

interface GrowthStats {
  /** Weak items and frequency of occurrence, in descending order of frequency, up to 5 items. */
  topWeaknesses: [string, number][];
  totalInterviews: number;
  totalPlans: number;
  totalWeakSkills: number;
  growthPct: number;
  growthLevel: string;
}

/** Aggregate page statistics from growth records: frequency of weak items, completion formula, and level labels. */
export function computeGrowthStats(records: GrowthRecord[]): GrowthStats {
  const count: Record<string, number> = {};
  for (const r of records) {
    for (const w of r.weak_skills) count[w] = (count[w] || 0) + 1;
  }
  const topWeaknesses = Object.entries(count)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);
  const totalInterviews = records.length;
  const totalPlans = records.reduce((sum, r) => sum + r.training_plan.length, 0);
  const totalWeakSkills = new Set(Object.keys(count)).size;
  const growthPct = Math.min(100, totalInterviews * 25 + Math.min(totalPlans, 4) * 5);
  // Level display words come from the message catalog; thresholds stay here.
  const t = getTranslator("growth");
  const growthLevel =
    totalInterviews === 0
      ? t("summary.level.none")
      : totalInterviews < 3
        ? t("summary.level.starting")
        : totalInterviews < 6
          ? t("summary.level.growing")
          : t("summary.level.advanced");
  return { topWeaknesses, totalInterviews, totalPlans, totalWeakSkills, growthPct, growthLevel };
}
