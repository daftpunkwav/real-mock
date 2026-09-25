"use client";

/**
 * AI growth-insight card: LLM cross-session analysis rendered above the
 * rule-based stats. Three states: empty (guide), generating (spinner), ready.
 */

import { Bot, CalendarClock, ListChecks, RefreshCw, Sparkles, TrendingUp, Wrench } from "lucide-react";
import { useT } from "@/i18n";
import { cn } from "@/lib/utils";
import type { GrowthInsight } from "@/lib/api/clients";
import { Section } from "./Section";

const STAGE_STYLES: Record<string, string> = {
  rising: "bg-[var(--success-soft)] text-[var(--success-ink)]",
  stalling: "bg-[var(--warning-soft)] text-[var(--warning-ink)]",
  plateau: "bg-[var(--info-soft)] text-[var(--info-ink)]",
  insufficient: "bg-surface-muted text-ink-subtle",
};

export function InsightCard({
  insight,
  status,
  onRefresh,
}: {
  insight: GrowthInsight | null;
  status: "loading" | "empty" | "generating" | "ready";
  onRefresh: () => void;
}) {
  const t = useT("growth");
  const stage = insight?.trajectory_stage ?? "";

  return (
    <Section
      title={t("insight.title")}
      icon={Sparkles}
      action={
        status === "ready" ? (
          <button
            type="button"
            onClick={onRefresh}
            className="flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[11px] text-ink-subtle transition-colors hover:bg-surface-muted hover:text-ink"
            title={t("insight.refresh")}
          >
            <RefreshCw size={11} />
            {t("insight.refresh")}
          </button>
        ) : null
      }
    >
      {status === "loading" || status === "generating" ? (
        <div className="flex items-center gap-2 py-8 text-[13px] text-ink-muted">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
          {status === "generating"
            ? t("insight.generating")
            : t("insight.loading")}
        </div>
      ) : !insight ? (
        <div className="py-8 text-center">
          <Bot className="mx-auto mb-2 text-ink-subtle" size={26} />
          <p className="mb-3 text-[13px] text-ink-subtle">{t("insight.empty")}</p>
          <button
            type="button"
            onClick={onRefresh}
            className="rounded-md bg-[var(--primary)] px-3 py-1.5 text-[12px] font-medium text-white transition-opacity hover:opacity-90"
          >
            {t("insight.generate")}
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={cn(
                "rounded-sm px-2 py-0.5 text-[11px] font-medium",
                STAGE_STYLES[stage] ?? STAGE_STYLES.insufficient,
              )}
            >
              {t(`insight.stage.${stage === "" ? "insufficient" : stage}`)}
            </span>
            <span className="text-[13px] font-medium text-ink">{insight.headline}</span>
          </div>

          <p className="text-[13px] leading-relaxed text-ink-muted">{insight.trajectory}</p>

          {insight.recurring_weaknesses.length > 0 ? (
            <div>
              <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-ink-subtle">
                <TrendingUp size={11} />
                {t("insight.patterns")}
              </p>
              <ul className="space-y-1.5">
                {insight.recurring_weaknesses.map((w) => (
                  <li key={w.skill} className="rounded-md bg-surface-muted px-2.5 py-2">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="min-w-0 break-words text-[12.5px] font-medium text-ink">
                        {w.skill}
                      </span>
                      <span className="shrink-0 text-[11px] text-ink-subtle">
                        {t("insight.appearedIn", { count: w.count })}
                        {" · "}
                        {t(`insight.trend.${w.trend === "" ? "stable" : w.trend}`)}
                      </span>
                    </div>
                    {w.advice ? (
                      <p className="mt-1 text-[12px] leading-relaxed text-ink-muted">{w.advice}</p>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {insight.improving_areas.length > 0 ? (
            <div>
              <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-ink-subtle">
                {t("insight.improving")}
              </p>
              <ul className="space-y-1">
                {insight.improving_areas.map((area) => (
                  <li key={area} className="flex items-start gap-2 text-[12.5px] text-ink-muted">
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-[var(--success)]" />
                    <span className="min-w-0 break-words">{area}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {insight.resume_gap_insights.length > 0 ? (
            <div>
              <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-ink-subtle">
                {t("insight.gaps")}
              </p>
              <ul className="space-y-1">
                {insight.resume_gap_insights.map((gap) => (
                  <li key={gap} className="flex items-start gap-2 text-[12.5px] text-ink-muted">
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-[var(--warning)]" />
                    <span className="min-w-0 break-words">{gap}</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {insight.training_plan.length > 0 ? (
            <div>
              <p className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.12em] text-ink-subtle">
                <ListChecks size={11} />
                {t("insight.plan")}
              </p>
              <div className="space-y-2">
                {insight.training_plan.map((focus) => (
                  <div key={focus.area} className="rounded-md border border-surface-border px-2.5 py-2">
                    <p className="text-[12.5px] font-medium text-ink">{focus.area}</p>
                    {focus.based_on ? (
                      <p className="mt-0.5 flex items-center gap-1 text-[11px] text-ink-subtle">
                        <CalendarClock size={10} />
                        {focus.based_on}
                      </p>
                    ) : null}
                    <ul className="mt-1 space-y-0.5">
                      {focus.actions.map((action) => (
                        <li key={action} className="flex items-start gap-1.5 text-[12px] text-ink-muted">
                          <Wrench size={10} className="mt-1 shrink-0 text-ink-subtle" />
                          <span className="min-w-0 break-words">{action}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <p className="text-right text-[10.5px] text-ink-subtle">
            {t("insight.basedOn", { count: insight.session_count })}
          </p>
        </div>
      )}
    </Section>
  );
}
