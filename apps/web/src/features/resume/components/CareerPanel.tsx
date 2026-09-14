"use client";

/**
 * @file CareerPanel.tsx
 * @description Career trajectory, stability, and gap notes.
 */

import { GitBranch } from "lucide-react";
import type { CareerAnalysisData } from "../types";
import { normalizeCnPunctuation } from "@/lib/cnText";
import { useT } from "@/i18n";
import { EvalRichText } from "./EvalRichText";
import { scoreColor } from "@/lib/scoreColor";

/* ── ─────────────────────────────── */

export function CareerPanel({ career }: { career: CareerAnalysisData }) {
  const t = useT("resume");
  const cn = normalizeCnPunctuation;
  const gaps = career.gaps ?? [];
  if (!career.trajectory && gaps.length === 0) return null;
  const stability = Math.max(0, Math.min(100, career.stability_score));
  const color = scoreColor(stability);

  return (
    <section className="eval-section">
      <span className="eval-label">{t("career.title")}</span>
      <div className="eval-career">
        <div className="eval-career-side">
          <div
            className="eval-career-gauge"
            style={{ background: `conic-gradient(${color} ${stability * 0.75}%, var(--muted) 0)` }}
            role="img"
            aria-label={t("career.gaugeAria", { score: stability })}
          >
            <span className="eval-career-gauge-inner">
              <span className="num-tabular eval-career-gauge-num" style={{ color }}>
                {stability}
              </span>
              <span className="eval-career-gauge-label">{t("career.gaugeLabel")}</span>
            </span>
          </div>
        </div>
        <div className="min-w-0 flex-1">
          {career.trajectory && (
            <p className="eval-career-trajectory">
              <GitBranch size={13} className="mt-1 shrink-0 text-[var(--primary)]" />
              <span>
                <EvalRichText text={cn(career.trajectory)} />
              </span>
            </p>
          )}
          {gaps.length > 0 && (
            <div className="eval-career-gaps">
              <p className="eval-career-gaps-label">{t("career.gaps")}</p>
              <ul>
                {gaps.map((g, i) => (
                  <li key={i}>
                    <EvalRichText text={cn(g)} />
                  </li>
                ))}
              </ul>
            </div>
          )}
          {career.notes && (
            <p className="eval-career-notes">{cn(career.notes)}</p>
          )}
        </div>
      </div>
    </section>
  );
}
