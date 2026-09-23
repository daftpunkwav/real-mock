"use client";

/**
 * @file page.tsx
 * @description Resume management page: upload, list, deep review, sticky preview.
 *
 * Responsibilities:
 * - Wire useResumeList into loading / error / ready UI states
 * - Keep ConfirmDialog on list items (shared component)
 *
 * Spinners use the shared Spinner. Do not reintroduce feature-local copies.
 */

import { LoadError } from "@/components/LoadError";
import { Spinner } from "@/components/Spinner";
import { useT } from "@/i18n";
import {
  useResumeList,
  ResumePageHead,
  ResumeUploadArea,
  ResumeList,
  ResumeDetailPanel,
  ResumePreviewCard,
  ResumeOverviewCard,
  ResumeTipsCard,
} from "@/features/resume";

export default function ResumePage() {
  const t = useT("resume");
  const {
    resumes,
    loading,
    loadError,
    uploading,
    analyzingIds,
    analyzeProgressById,
    uploadError,
    analyzeError,
    previewId,
    inputRef,
    previewResume,
    analysis,
    setPreviewId,
    load,
    handleUpload,
    handleUploadVersion,
    handleAnalyze,
    handleActivate,
    handleDelete,
    handleRetryParse,
  } = useResumeList();

  return (
    <div className="page-shell anim-rise">
      <ResumePageHead />

      {loading ? (
        <div className="flex items-center justify-center gap-2 py-16 text-[13px] text-ink-muted">
          <Spinner />
          {t("page.loading")}
        </div>
      ) : loadError ? (
        <LoadError message={loadError} onRetry={load} />
      ) : (
        <div className="grid grid-cols-1 items-start gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
          {/* ===== Left:Uploading + LIST + In-depth reviews ===== */}
          <div className="min-w-0 space-y-4">
            <ResumeUploadArea
              uploading={uploading}
              error={uploadError}
              inputRef={inputRef}
              onUpload={handleUpload}
            />

            <ResumeList
              resumes={resumes}
              previewId={previewId}
              analyzingIds={analyzingIds}
              uploading={uploading}
              onSelect={setPreviewId}
              onActivate={handleActivate}
              onAnalyze={handleAnalyze}
              onDelete={handleDelete}
              onUploadVersion={handleUploadVersion}
              onRetryParse={handleRetryParse}
            />

            <ResumeDetailPanel
              resume={previewResume}
              analysis={analysis}
              familyRows={resumes}
              analyzingIds={analyzingIds}
              analyzeProgress={
                previewResume ? analyzeProgressById[previewResume.id] : undefined
              }
              error={analyzeError}
              onAnalyze={handleAnalyze}
            />
          </div>

          {/* ===== Right: compact sticky preview ===== */}
          <aside className="space-y-3 xl:sticky xl:top-6">
            <ResumePreviewCard resume={previewResume} />
            <ResumeOverviewCard resumes={resumes} />
            <ResumeTipsCard />
          </aside>
        </div>
      )}
    </div>
  );
}
