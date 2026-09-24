"use client";

/**
 * @file AnalysisPanel.tsx
 * @description Deep-review sheet: masthead, impression, and content tabs.
 *
 * Responsibilities:
 * - Derive radar rows from dimension_scores
 * - Show only tabs that have content (analysisTabs)
 *
 * Tab visibility lives in analysisTabs.ts; this component owns icons and layout.
 * Tab bodies are swapped by React state only — wrapping them in AnimatePresence
 * left the previous panel mounted after aria-selected moved (React 19 + FM 12).
 */

import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Briefcase,
  Compass,
  FileStack,
  LayoutList,
  Lightbulb,
  MessagesSquare,
} from "lucide-react";
import { useT } from "@/i18n";
import type { ResumeAnalysis } from "../types";
import type { ResumeItem } from "../resumeNormalize";
import { visibleAnalysisTabIds, TAB_LABEL_KEYS, type TabId } from "../analysisTabs";
import { DIM_LABEL_KEYS, dimComment, dimScore, percentileFromScore, type RadarDim } from "../analysisFormat";
import { EvalRichText } from "./EvalRichText";
import { ScoreRing } from "./ScoreRing";
import { FirstImpressionCard, HeadlineBanner } from "./ImpressionCards";
import { OverviewTab } from "./OverviewTab";
import { DocumentTab } from "./DocumentTab";
import { ProjectsTab } from "./ProjectsTab";
import { InterviewTab } from "./InterviewTab";
import { AdviceTab } from "./AdviceTab";
import { CareerTab } from "./CareerTab";

const TAB_ICONS: Record<TabId, React.ReactNode> = {
  overview: <LayoutList size={13} />,
  document: <FileStack size={13} />,
  projects: <Briefcase size={13} />,
  interview: <MessagesSquare size={13} />,
  advice: <Lightbulb size={13} />,
  career: <Compass size={13} />,
};

export function AnalysisPanel({
  analysis,
  familyRows = [],
  currentId,
}: {
  analysis: ResumeAnalysis;
  familyRows?: ResumeItem[];
  currentId?: number;
}) {
  const t = useT("resume");
  const dims = analysis.dimension_scores || {};
  const radarDims: RadarDim[] = Object.entries(dims).map(([key, v]) => {
    const labelKey = DIM_LABEL_KEYS[key];
    return {
      key,
      label: labelKey ? t(labelKey) : key,
      score: dimScore(v),
      comment: dimComment(v),
    };
  });
  // Recompute from overall score so pre-migration LLM percentiles are not shown as peer rank.
  const percentile =
    typeof analysis.score === "number" ? percentileFromScore(analysis.score) : null;

  const tabs = useMemo(() => {
    const ids = visibleAnalysisTabIds(analysis);
    return ids.map((id) => ({
      id,
      label: t(TAB_LABEL_KEYS[id]),
      icon: TAB_ICONS[id],
    }));
  }, [analysis, t]);

  const [tab, setTab] = useState<TabId>("overview");
  const activeTab = tabs.some((x) => x.id === tab) ? tab : "overview";

  return (
    <article className="eval-sheet">
      <header className="eval-masthead">
        <div className="min-w-0">
          <h2 className="eval-masthead-title">{t("analysis.mastheadTitle")}</h2>
          <p className="eval-masthead-sub">{t("analysis.mastheadSub")}</p>
        </div>
        <div className="eval-masthead-stats">
          <ScoreRing score={analysis.score} />
          <div className="eval-masthead-meta">
            {analysis.seniority_estimate?.trim() ? (
              <p>
                {t("overview.seniorityLabel")} ·{" "}
                <strong>
                  <EvalRichText text={analysis.seniority_estimate} />
                </strong>
              </p>
            ) : null}
            {percentile != null ? (
              <p>
                {t("overview.percentileTitle")} · <strong>{percentile}</strong>
              </p>
            ) : null}
          </div>
        </div>
      </header>

      {analysis.headline?.trim() && <HeadlineBanner text={analysis.headline} />}

      {analysis.first_impression?.trim() && (
        <FirstImpressionCard text={analysis.first_impression} />
      )}

      {tabs.length > 1 && (
        <div className="eval-tabs" role="tablist" aria-label={t("analysis.tabsAria")}>
          {tabs.map((x) => (
            <button
              key={x.id}
              type="button"
              role="tab"
              id={`resume-analysis-tab-${x.id}`}
              aria-controls="resume-analysis-panel"
              aria-selected={activeTab === x.id}
              onClick={() => setTab(x.id)}
              className={`eval-tab ${activeTab === x.id ? "is-active" : ""}`}
            >
              {x.icon}
              {x.label}
              {activeTab === x.id && (
                <motion.span
                  layoutId="eval-tab-underline"
                  className="eval-tab-underline"
                  transition={{ type: "spring", stiffness: 420, damping: 34 }}
                />
              )}
            </button>
          ))}
        </div>
      )}

      <div
        className="eval-tabpanel"
        role="tabpanel"
        id="resume-analysis-panel"
        aria-labelledby={`resume-analysis-tab-${activeTab}`}
      >
        {activeTab === "overview" && (
          <OverviewTab
            analysis={analysis}
            radarDims={radarDims}
            percentile={percentile}
            familyRows={familyRows}
            currentId={currentId}
          />
        )}
        {activeTab === "document" && <DocumentTab analysis={analysis} />}
        {activeTab === "projects" && <ProjectsTab analysis={analysis} />}
        {activeTab === "interview" && <InterviewTab analysis={analysis} />}
        {activeTab === "advice" && <AdviceTab analysis={analysis} />}
        {activeTab === "career" && <CareerTab analysis={analysis} />}
      </div>
    </article>
  );
}
