"use client";

/** Deep report page: overview / per-turn analysis / verdict / plan tabs. */

import { useParams } from "next/navigation";
import Link from "next/link";
import { useState } from "react";
import { RefreshCw } from "lucide-react";
import { useT } from "@/i18n";
import { useReportLoad } from "@/features/report/useReportLoad";
import {
  REPORT_TAB_IDS,
  REPORT_TAB_LABEL_KEYS,
  defaultReportTab,
  visibleReportTabIds,
  type ReportTabId,
} from "@/features/report/reportTabs";
import { normalizeScores } from "@/features/report/scoreFormat";
import { ScoreSummaryCard } from "@/features/report/components/ScoreSummaryCard";
import { ShortSessionAlert } from "@/features/report/components/ShortSessionAlert";
import { DimensionScores } from "@/features/report/components/DimensionScores";
import { ScoreRadar } from "@/features/report/components/ScoreRadar";
import { Section } from "@/features/report/components/Section";
import { FaceAnalysisCard } from "@/features/report/components/FaceAnalysisCard";
import { ActionLinks } from "@/features/report/components/ActionLinks";
import { VerdictBanner } from "@/features/report/components/VerdictBanner";
import { TurnDeepNotes } from "@/features/report/components/TurnDeepNotes";
import { ReportLiveProgress } from "@/features/report/components/ReportLiveProgress";
import { PhaseOverviewCard } from "@/features/report/components/PhaseOverviewCard";
import { ExternalNotesCard } from "@/features/report/components/ExternalNotesCard";

export default function ReportPage() {
  const params = useParams();
  const t = useT("report");
  const sessionId = Number(params.id);
  const {
    report,
    ledger,
    duration,
    messagesCount,
    loading,
    error,
    generating,
    live,
    retryGenerate,
  } = useReportLoad(sessionId);
  const [activeTab, setActiveTab] = useState<ReportTabId | null>(null);

  if (generating && !report) {
    return <ReportLiveProgress live={live} />;
  }

  if (loading) {
    return (
      <div className="page-shell flex min-h-[40vh] items-center justify-center gap-2 text-[13px] text-ink-muted">
        <span className="block h-4 w-4 anim-spin rounded-full border-2 border-current border-t-transparent" />
        {t("page.loading")}
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="page-shell py-16 text-center">
        <p className="mb-4 text-[13px] text-ink-muted">{error || t("errors.unavailable")}</p>
        <div className="flex flex-wrap justify-center gap-2.5">
          {Number.isFinite(sessionId) && sessionId > 0 && (
            <button type="button" className="btn-secondary" onClick={retryGenerate}>
              <RefreshCw size={13} /> {t("page.retryCta")}
            </button>
          )}
          <Link href="/interview" className="btn-primary">
            {t("page.backToInterview")}
          </Link>
        </div>
      </div>
    );
  }

  const scores = normalizeScores(report.score_breakdown);
  const shortSession =
    (typeof messagesCount === "number" && messagesCount < 6) ||
    (typeof duration === "number" && duration < 5);
  const tabs = visibleReportTabIds(report);
  const current = activeTab && tabs.includes(activeTab) ? activeTab : defaultReportTab(report);

  return (
    <div className="page-shell anim-rise">
      <VerdictBanner verdict={report.verdict} reasoning={report.verdict_reasoning} />

      <nav className="eval-tabs mt-4" role="tablist">
        {REPORT_TAB_IDS.filter((id) => tabs.includes(id)).map((id) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={current === id}
            className={`eval-tab ${current === id ? "is-active" : ""}`}
            onClick={() => setActiveTab(id)}
          >
            {t(REPORT_TAB_LABEL_KEYS[id])}
          </button>
        ))}
      </nav>

      {current === "overview" && (
        <div role="tabpanel">
          <ScoreSummaryCard
            duration={duration}
            messagesCount={messagesCount}
            overallScore={report.overall_score}
          />
          <ShortSessionAlert show={shortSession} />
          <DimensionScores scores={scores} />
          <ScoreRadar scores={scores} />
          <Section title={t("sections.strengths")} items={report.strengths} tone="success" />
          <Section title={t("sections.weaknesses")} items={report.weaknesses} tone="danger" />
          <PhaseOverviewCard summary={report.phase_summary} />
        </div>
      )}

      {current === "turns" && (
        <div role="tabpanel">
          <TurnDeepNotes notes={report.turn_notes} ledger={ledger} />
        </div>
      )}

      {current === "verdict" && (
        <div role="tabpanel">
          <VerdictBanner verdict={report.verdict} reasoning={report.verdict_reasoning} />
          {report.verdict === "passed" && (
            <Section
              title={t("sections.highlights")}
              items={report.highlights}
              tone="success"
            />
          )}
          {report.verdict === "failed" && (
            <Section
              title={t("sections.keyProblems")}
              items={report.key_problems}
              tone="danger"
            />
          )}
          {report.presence_moments && report.presence_moments.length > 0 && (
            <Section
              title={t("sections.presenceMoments")}
              items={report.presence_moments}
              tone="brand"
            />
          )}
          {report.face_analysis_summary && (
            <FaceAnalysisCard summary={report.face_analysis_summary} />
          )}
          <ExternalNotesCard notes={report.external_notes} />
        </div>
      )}

      {current === "plan" && (
        <div role="tabpanel">
          <Section title={t("sections.trainingPlan")} items={report.training_plan} tone="warning" />
          <Section
            title={t("sections.improvementSuggestions")}
            items={report.improvement_suggestions}
            tone="brand"
          />
          <Section
            title={t("sections.resumeSuggestions")}
            items={report.resume_suggestions || []}
            tone="brand"
          />
          <Section
            title={t("sections.interviewSuggestions")}
            items={report.interview_suggestions || []}
            tone="brand"
          />
        </div>
      )}

      <ActionLinks />
    </div>
  );
}
