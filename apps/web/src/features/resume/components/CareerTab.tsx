"use client";

/**
 * @file CareerTab.tsx
 * @description Career and market tab: trajectory, salary, company fit, market insights.
 */

import type { ResumeAnalysis } from "../types";
import { normalizeCnPunctuation } from "@/lib/cnText";
import { useT } from "@/i18n";
import { EvalRichText } from "./EvalRichText";
import { EvalList } from "./EvalList";
import { CareerPanel } from "./CareerPanel";
import { CompanyFitBars } from "./CompanyFitBars";

export function CareerTab({ analysis }: { analysis: ResumeAnalysis }) {
  const t = useT("resume");
  const cn = normalizeCnPunctuation;
  return (
    <>
      {analysis.career_analysis && <CareerPanel career={analysis.career_analysis} />}

      {analysis.salary_positioning?.trim() && (
        <section className="eval-callout">
          <span className="eval-label">{t("career.salary")}</span>
          <p className="eval-prose eval-prose-sm eval-prose-fill">
            <EvalRichText text={cn(analysis.salary_positioning)} />
          </p>
        </section>
      )}

      {analysis.company_fit && analysis.company_fit.length > 0 && (
        <CompanyFitBars fits={analysis.company_fit} />
      )}

      {analysis.market_insights && analysis.market_insights.length > 0 && (
        <EvalList title={t("career.market")} items={analysis.market_insights.map(cn)} />
      )}
    </>
  );
}
