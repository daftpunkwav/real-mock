"use client";

/**
 * @file AdviceTab.tsx
 * @description Resume advice tab: strengths, weaknesses, red flags, improvement
 * suggestions, rewrites, keywords, skill trust.
 */

import { AlertTriangle } from "lucide-react";
import type { ResumeAnalysis } from "../types";
import { normalizeCnPunctuation } from "@/lib/cnText";
import { useT } from "@/i18n";
import { EvalRichText } from "./EvalRichText";
import { EvalList } from "./EvalList";
import { RewriteGallery } from "./RewriteGallery";
import { SkillTrustBoard } from "./SkillTrustBoard";

export function AdviceTab({ analysis }: { analysis: ResumeAnalysis }) {
  const t = useT("resume");
  const cn = normalizeCnPunctuation;
  return (
    <>
      <div className="eval-pair">
        {analysis.strengths && analysis.strengths.length > 0 && (
          <EvalList title={t("advice.strengths")} items={analysis.strengths.map(cn)} />
        )}
        {analysis.weaknesses && analysis.weaknesses.length > 0 && (
          <EvalList title={t("advice.weaknesses")} items={analysis.weaknesses.map(cn)} />
        )}
      </div>

      {analysis.red_flags && analysis.red_flags.length > 0 && (
        <div className="alert alert-error !py-4">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <div className="min-w-0">
            <p className="mb-2.5 text-sm font-semibold tracking-[0.06em]">{t("advice.redFlags")}</p>
            <ul className="eval-list">
              {analysis.red_flags.map((s, i) => (
                <li key={i}>
                  <span className="eval-list-mark">·</span>
                  <span className="eval-list-body">
                    <EvalRichText text={cn(s)} />
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {analysis.improvement_suggestions && analysis.improvement_suggestions.length > 0 && (
        <EvalList
          title={t("advice.improvements")}
          items={analysis.improvement_suggestions.map(cn)}
        />
      )}

      {analysis.rewrite_examples && analysis.rewrite_examples.length > 0 && (
        <RewriteGallery items={analysis.rewrite_examples} />
      )}

      {analysis.skill_trust && <SkillTrustBoard trust={analysis.skill_trust} />}

      {analysis.ats_keywords?.length || analysis.missing_keywords?.length ? (
        <div className="eval-kw-grid">
          {!!analysis.ats_keywords?.length && (
            <section className="eval-section min-w-0">
              <span className="eval-label">{t("advice.coveredKeywords")}</span>
              <div className="eval-kw is-covered">
                {analysis.ats_keywords.map((k) => (
                  <span key={k}>{k}</span>
                ))}
              </div>
            </section>
          )}
          {!!analysis.missing_keywords?.length && (
            <section className="eval-section min-w-0">
              <span className="eval-label">{t("advice.suggestedKeywords")}</span>
              <ul className="eval-kw-suggest">
                {analysis.missing_keywords.map((k) => (
                  <li key={k}>
                    <EvalRichText text={cn(k)} />
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      ) : null}
    </>
  );
}
