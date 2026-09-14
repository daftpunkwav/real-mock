"use client";

/** Interview setup page; useInterviewSetup owns its state and data loading. */

import { useT } from "@/i18n";
import { Play } from "lucide-react";
import { LoadError } from "@/components/LoadError";
import { useInterviewSetup } from "@/features/interview/hooks/useInterviewSetup";
import {
  ContinueProcesses,
  useProcessContinuation,
} from "@/features/interview/processes";
import { SetupFields } from "@/features/interview/setup/fields";
import { SetupHeader, SetupLoading, SetupMain } from "@/features/interview/setup/shell";
import { InterviewPreview } from "@/features/interview/setup/preview";

export default function InterviewSetupPage() {
  const {
    options,
    resumes,
    loading,
    loadError,
    creating,
    config,
    multiRound,
    chatModels,
    sttModels,
    ttsModels,
    chatModelId,
    sttModelId,
    ttsModelId,
    effort,
    referenceDetail,
    defaultBindings,
    set,
    setMultiRound,
    setChatModelId,
    setSttModelId,
    setTtsModelId,
    setEffort,
    setReferenceDetail,
    reload,
    start,
  } = useInterviewSetup();
  const continuation = useProcessContinuation();
  const t = useT("interview");

  const startButton = (fullWidth = false) => (
    <button
      type="button"
      className={`btn-primary shrink-0 ${fullWidth ? "w-full" : ""}`}
      onClick={start}
      disabled={creating || loading || !!loadError}
    >
      {creating ? (
        <span className="block h-3.5 w-3.5 anim-spin rounded-full border-2 border-current border-t-transparent" />
      ) : (
        <Play size={14} className="btn-arrow transition-transform" />
      )}
      {t("setup.start")}
    </button>
  );

  return (
    <div className="page-shell flex h-full min-h-0 flex-col overflow-hidden !pb-4 anim-rise">
      <SetupHeader action={!loading && !loadError && options ? startButton(false) : undefined} />
      <ContinueProcesses
        processes={continuation.processes}
        loading={continuation.loading}
        startingId={continuation.startingId}
        onStart={continuation.startNext}
      />
      {loading ? (
        <SetupLoading />
      ) : loadError ? (
        <LoadError message={loadError} onRetry={reload} />
      ) : options ? (
        <SetupMain
          left={
            <SetupFields
              options={options}
              config={config}
              resumes={resumes}
              creating={creating}
              multiRound={multiRound}
              onMultiRound={setMultiRound}
              chatModels={chatModels}
              sttModels={sttModels}
              ttsModels={ttsModels}
              chatModelId={chatModelId}
              sttModelId={sttModelId}
              ttsModelId={ttsModelId}
              effort={effort}
              referenceDetail={referenceDetail}
              defaultBindings={defaultBindings}
              onConfig={set}
              setChatModelId={setChatModelId}
              setSttModelId={setSttModelId}
              setTtsModelId={setTtsModelId}
              setEffort={setEffort}
              setReferenceDetail={setReferenceDetail}
              footer={
                <div className="sticky bottom-0 shrink-0 bg-[var(--background)]/90 pb-1 pt-1 backdrop-blur-sm sm:hidden">
                  {startButton(true)}
                </div>
              }
            />
          }
          preview={<InterviewPreview options={options} config={config} resumes={resumes} />}
        />
      ) : null}
    </div>
  );
}
