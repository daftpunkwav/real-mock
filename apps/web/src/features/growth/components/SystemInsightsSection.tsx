"use client";

import { BarChart3 } from "lucide-react";
import type { SystemInsights } from "../types";
import { useT } from "@/i18n";
import { Section } from "./Section";

/** System Self-Growth Block: Aggregated Summary Across Interviews + Company Distribution + Recent Leads. */
export function SystemInsightsSection({ insights }: { insights: SystemInsights }) {
  const t = useT("growth");
  return (
    <Section title={t("insights.title")} icon={BarChart3}>
      <p className="mb-3 text-[11px] leading-relaxed text-ink-subtle">
        {t("insights.description")}
        {insights.interview_tools_enabled ? t("insights.toolsOn") : t("insights.toolsOff")}
        {insights.github_token_configured
          ? t("insights.githubConfigured")
          : t("insights.githubMissing")}
      </p>
      <div className="mb-3 grid grid-cols-2 gap-2">
        {Object.entries(insights.company_session_counts || {})
          .slice(0, 6)
          .map(([k, v]) => (
            <div
              key={k}
              className="kpi-card flex !flex-row items-center justify-between gap-2 !p-2.5"
            >
              <span className="truncate text-[11px] text-ink-muted">{k}</span>
              <span className="font-mono text-[12px] font-semibold text-ink num-tabular">
                {t("insights.sessionCount", { count: v })}
              </span>
            </div>
          ))}
      </div>
      {insights.recent_probes && insights.recent_probes.length > 0 && (
        <div>
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-ink-subtle">
            {t("insights.recentProbes")}
          </p>
          <ul className="max-h-32 space-y-2 overflow-y-auto text-[11px] leading-relaxed text-ink-muted">
            {insights.recent_probes.slice(0, 5).map((p, i) => (
              <li key={i} className="break-words">
                {t("insights.probeItem", { company: p.company || "—", point: p.point ?? "" })}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Section>
  );
}
