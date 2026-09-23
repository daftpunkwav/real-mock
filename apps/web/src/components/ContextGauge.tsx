"use client";

/** Context usage ring and token breakdown panel. */

import { memo, useState } from "react";
import { formatTokenCount, useT } from "@/i18n";

/** Format tokens via formatTokenCount (wan/K/M); non-positive or non-finite → "0". */
export function formatTokens(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return "0";
  return formatTokenCount(Math.round(n));
}

/** Context usage ring with a track and rounded progress arc. */
export const ContextRing = memo(function ContextRing({
  ratio,
  title,
}: {
  ratio: number;
  title?: string;
}) {
  const t = useT("common");
  const pct = Math.max(0, Math.min(1, Number.isFinite(ratio) ? ratio : 0));
  const r = 6;
  const c = 2 * Math.PI * r;
  const color =
    pct >= 0.9
      ? "var(--danger)"
      : pct >= 0.7
        ? "var(--warning)"
        : "var(--primary)";
  const label = title ?? t("context.usage", { percent: `${Math.round(pct * 100)}%` });
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 14 14"
      className="shrink-0"
      role="img"
      aria-label={label}
    >
      <title>{label}</title>
      <circle cx="7" cy="7" r={r} fill="none" stroke="var(--border)" strokeWidth="2" />
      {pct > 0 && (
        <circle
          cx="7"
          cy="7"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="2"
          strokeDasharray={`${c * pct} ${c}`}
          strokeLinecap="round"
          transform="rotate(-90 7 7)"
        />
      )}
    </svg>
  );
});

export interface ContextBucket {
  label: string;
  /** Estimated token count used to calculate proportions. */
  value: number;
  color: string;
  /** Plain-language explanation shown as a tooltip. */
  hint?: string;
}

/** Provider-reported token usage; cache rate is cached divided by prompt.
 * Request diagnostics are optional best-effort fields (provider-dependent). */
export interface UsageSummary {
  prompt_tokens: number;
  completion_tokens: number;
  cached_tokens: number;
  reasoning_tokens?: number;
  /** Provider requests made for the measured span (turn or session). */
  requests?: number;
  /** Upstream request id of the most recent request (echo header). */
  last_request_id?: string;
  /** Wall-clock latency of the most recent request in milliseconds. */
  last_latency_ms?: number;
  /** Compact summary of the most recent failed request, empty when none. */
  last_error?: string;
}

/** Clickable context gauge with measured buckets and provider-reported usage. */
export const ContextGauge = memo(function ContextGauge({
  used,
  window: win,
  breakdown,
  usage,
  estimatedPrompt,
}: {
  used: number;
  /** Context window size; 0 means no model window is known. */
  window: number;
  /** Measured usage categories and their colors. */
  breakdown: ContextBucket[];
  /** Optional provider-reported token usage. */
  usage?: UsageSummary | null;
  /**
   * Mechanical input estimate used only when the provider reported no prompt
   * usage (some providers report completion-only deltas). Displayed with an
   * estimated marker, never persisted as truth.
   */
  estimatedPrompt?: number | null;
}) {
  const [open, setOpen] = useState(false);
  const t = useT("common");
  const pct = win ? Math.max(0, Math.min(1, used / win)) : 0;
  const color =
    pct >= 0.9 ? "var(--danger)" : pct >= 0.7 ? "var(--warning)" : "var(--primary)";
  const total = breakdown.reduce((s, b) => s + b.value, 0) || 1;
  const reportedPrompt = usage?.prompt_tokens ?? 0;
  const reportedCompletion = usage?.completion_tokens ?? 0;
  // Provider truth wins; otherwise fall back to the mechanical estimate
  // (flagged as estimated). Both zero means genuinely no data yet.
  const inputEstimated = reportedPrompt <= 0 && (estimatedPrompt ?? 0) > 0;
  const inputValue = reportedPrompt > 0 ? reportedPrompt : (estimatedPrompt ?? 0);
  const hasUsage = inputValue > 0 || reportedCompletion > 0;
  const cacheRate =
    reportedPrompt > 0
      ? Math.min(1, (usage?.cached_tokens ?? 0) / reportedPrompt)
      : null;

  return (
    <div className="relative shrink-0">
      <button
        type="button"
        className="flex items-center rounded-full p-0.5 transition-colors hover:bg-surface-muted"
        onClick={() => setOpen((v) => !v)}
        aria-label={t("context.usageAria")}
        aria-expanded={open}
      >
        <ContextRing
          ratio={pct}
          title={t("context.usage", { percent: `${Math.round(pct * 100)}%` })}
        />
      </button>

      {open && (
        <>
          {/* Click outside the panel to close */}
          <div className="fixed inset-0 z-30" onClick={() => setOpen(false)} aria-hidden />
          <div className="surface-card absolute bottom-full right-0 z-40 mb-2 w-72 !p-3 shadow-lg">
            <div className="flex items-baseline justify-between">
              <p className="text-[12px] font-semibold text-ink">{t("context.panel.title")}</p>
              <p className="num-tabular text-[11px] text-ink-muted">
                {win
                  ? t("context.panel.usage", {
                      used: formatTokens(used),
                      total: formatTokens(win),
                      percent: `${Math.round(pct * 100)}%`,
                    })
                  : t("context.panel.usageNoModel", { used: formatTokens(used) })}
              </p>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-muted">
              <div
                className="h-full rounded-full transition-all"
                style={{ width: `${pct * 100}%`, backgroundColor: color }}
              />
            </div>
            <div className="mt-2.5 space-y-1.5">
              {breakdown.map((b) => (
                <div key={b.label} className="flex items-center gap-2 text-[11px]" title={b.hint}>
                  <span
                    className="h-1.5 w-1.5 shrink-0 rounded-full"
                    style={{ backgroundColor: b.color }}
                  />
                  <span className="min-w-0 flex-1 cursor-help text-ink-muted">{b.label}</span>
                  <span className="num-tabular text-ink-subtle">
                    {Math.round((b.value / total) * 100)}%
                  </span>
                </div>
              ))}
              {breakdown.length === 0 && (
                <p className="text-[11px] text-ink-subtle">{t("context.noMessages")}</p>
              )}
            </div>
            {hasUsage && (
              <>
                <div className="my-2.5 border-t border-surface-border" />
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="text-ink-muted">{t("context.promptTokens")}</span>
                    <span className="num-tabular text-ink-subtle">
                      {formatTokens(inputValue)}
                      {inputEstimated && (
                        <span
                          className="ml-1 rounded bg-surface-muted px-1 text-[10px]"
                          title={t("context.estimatedHint")}
                        >
                          {t("context.estimated")}
                        </span>
                      )}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="text-ink-muted">{t("context.completionTokens")}</span>
                    <span className="num-tabular text-ink-subtle">
                      {formatTokens(reportedCompletion)}
                    </span>
                  </div>
                  {(usage?.reasoning_tokens ?? 0) > 0 && (
                    <div
                      className="flex items-center justify-between text-[11px]"
                      title={t("context.reasoningHint")}
                    >
                      <span className="pl-2 text-ink-subtle">{t("context.reasoningTokens")}</span>
                      <span className="num-tabular text-ink-subtle">
                        {formatTokens(usage?.reasoning_tokens ?? 0)}
                      </span>
                    </div>
                  )}
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="text-ink-muted">{t("context.cacheRate")}</span>
                    <span className="num-tabular text-ink-subtle">
                      {cacheRate != null
                        ? t("context.cacheRateValue", {
                            percent: `${Math.round(cacheRate * 100)}%`,
                            tokens: formatTokens(usage!.cached_tokens),
                          })
                        : "—"}
                    </span>
                  </div>
                </div>
              </>
            )}
            {(usage?.requests ?? 0) > 0 && (
              <>
                <div className="my-2.5 border-t border-surface-border" />
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between text-[11px]">
                    <span className="text-ink-muted">{t("context.requests")}</span>
                    <span className="num-tabular text-ink-subtle">{usage?.requests}</span>
                  </div>
                  {(usage?.last_latency_ms ?? 0) > 0 && (
                    <div
                      className="flex items-center justify-between text-[11px]"
                      title={usage?.last_request_id ? `request id: ${usage.last_request_id}` : undefined}
                    >
                      <span className="text-ink-muted">{t("context.lastLatency")}</span>
                      <span className="num-tabular text-ink-subtle">
                        {t("context.latencyValue", {
                          ms: Math.round(usage?.last_latency_ms ?? 0).toLocaleString(),
                        })}
                      </span>
                    </div>
                  )}
                  {usage?.last_error ? (
                    <div className="flex items-start justify-between gap-2 text-[11px]">
                      <span className="shrink-0 text-[var(--danger)]">{t("context.lastError")}</span>
                      <span className="min-w-0 break-all text-right text-ink-subtle" title={usage.last_error}>
                        {usage.last_error.length > 80
                          ? `${usage.last_error.slice(0, 80)}…`
                          : usage.last_error}
                      </span>
                    </div>
                  ) : null}
                </div>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
});
