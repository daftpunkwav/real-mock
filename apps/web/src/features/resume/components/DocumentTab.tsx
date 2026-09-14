"use client";

/**
 * @file DocumentTab.tsx
 * @description Layout / typography / content critiques plus the section review heatmap.
 */

import type { ResumeAnalysis } from "../types";
import { normalizeCnPunctuation } from "@/lib/cnText";
import { useT } from "@/i18n";
import { EvalRichText } from "./EvalRichText";
import { SectionHeatmap } from "./SectionHeatmap";

export function DocumentTab({ analysis }: { analysis: ResumeAnalysis }) {
  const t = useT("resume");
  const cn = normalizeCnPunctuation;
  return (
    <>
      {analysis.layout_review ? (
        <section className="eval-section">
          <span className="eval-label">{t("document.layout")}</span>
          <p className="eval-prose eval-prose-sm eval-prose-fill">
            <EvalRichText text={cn(analysis.layout_review)} />
          </p>
        </section>
      ) : null}
      {analysis.typography_review ? (
        <section className="eval-section">
          <span className="eval-label">{t("document.typography")}</span>
          <p className="eval-prose eval-prose-sm eval-prose-fill">
            <EvalRichText text={cn(analysis.typography_review)} />
          </p>
        </section>
      ) : null}
      {analysis.content_review ? (
        <section className="eval-section">
          <span className="eval-label">{t("document.content")}</span>
          <p className="eval-prose eval-prose-sm eval-prose-fill">
            <EvalRichText text={cn(analysis.content_review)} />
          </p>
        </section>
      ) : null}
      {analysis.section_reviews && analysis.section_reviews.length > 0 && (
        <SectionHeatmap reviews={analysis.section_reviews} />
      )}
    </>
  );
}
