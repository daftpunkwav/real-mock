"use client";

/**
 * @file InterviewTab.tsx
 * @description Interview drill tab: predicted Q&A cards, follow-up questions, risk areas.
 * Uses the shared InterviewQaCard for each drill item.
 */

import type { ResumeAnalysis } from "../types";
import { normalizeCnPunctuation } from "@/lib/cnText";
import { useT } from "@/i18n";
import { EvalList } from "./EvalList";
import { EvalNumberedStack } from "./EvalNumberedStack";
import { InterviewQaCard } from "./InterviewQaCard";

export function InterviewTab({ analysis }: { analysis: ResumeAnalysis }) {
  const t = useT("resume");
  const cn = normalizeCnPunctuation;
  const qa = analysis.interview_qa ?? [];
  return (
    <>
      {qa.length > 0 && (
        <section className="eval-section">
          <span className="eval-label">{t("interview.qaTitle")}</span>
          <div className="space-y-3">
            {qa.map((item, i) => (
              <InterviewQaCard key={i} item={item} index={i} />
            ))}
          </div>
        </section>
      )}

      {analysis.predicted_questions && analysis.predicted_questions.length > 0 && (
        <EvalNumberedStack
          title={t("interview.predicted")}
          prefix="Q"
          items={analysis.predicted_questions.map(cn)}
        />
      )}

      {analysis.interview_risk_areas && analysis.interview_risk_areas.length > 0 && (
        <EvalList title={t("interview.riskAreas")} items={analysis.interview_risk_areas.map(cn)} />
      )}
    </>
  );
}
