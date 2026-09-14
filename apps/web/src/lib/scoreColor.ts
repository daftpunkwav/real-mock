/** Score → color band (single global impl shared by report and resume).
 *
 * Bands: ≥85 success / ≥70 primary / ≥60 warning / else danger;
 * null or non-finite → muted-foreground; callers decide whether to show.
 */
export function scoreColor(score: number | null | undefined): string {
  if (score == null || Number.isNaN(score)) return "var(--muted-foreground)";
  if (score >= 85) return "var(--success)";
  if (score >= 70) return "var(--primary)";
  if (score >= 60) return "var(--warning)";
  return "var(--danger)";
}

/** Peer percentile → color band (competitive-percentile thresholds differ from 0–100 score bands). */
export function percentileColor(pct: number | null | undefined): string {
  if (pct == null || Number.isNaN(pct)) return "var(--muted-foreground)";
  if (pct >= 75) return "var(--success)";
  if (pct >= 45) return "var(--primary)";
  if (pct >= 25) return "var(--warning)";
  return "var(--danger)";
}
