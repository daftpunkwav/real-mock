"use client";

/**
 * @file page.tsx
 * @description AI prep-coach chat page; usePrepChat owns session state and streaming.
 */

import { useMemo } from "react";
import { BookOpen, ArrowDown } from "lucide-react";
import { useT } from "@/i18n";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import {
  AskUserModal,
  AssistantBubble,
  CompactionCard,
  PrepComposer,
  PrepEmptyState,
  PrepSidePanel,
  RateModal,
  UserBubble,
  usePrepChat,
} from "@/features/prep";
import type { PrepChatMessage } from "@/features/prep";

export default function PrepPage() {
  const t = useT("prep");
  const chat = usePrepChat();
  const {
    messages,
    input,
    setInput,
    loading,
    compacting,
    busySids,
    stopSession,
    starting,
    prepError,
    switchError,
    switchFailedId,
    clearSwitchError,
    prepSessionId,
    sessions,
    askDialog,
    resumes,
    resumeId,
    setResumeId,
    resumeLoadError,
    chatModels,
    selectedModelId,
    setSelectedModelId,
    defaultChatProfile,
    effort,
    setEffort,
    tokenUsage,
    usage,
    contextBuckets,
    contextTotal,
    reportedContext,
    estimatedPrompt,
    showJump,
    chatScrollRef,
    contentRef,
    handleSend,
    handleStop,
    pendingRefs,
    addRef,
    removeRef,
    handleSlashCommand,
    slashClearOpen,
    confirmSlashClear,
    cancelSlashClear,
    handleAskAnswer,
    handleQuickPrompt,
    handleNewSession,
    handleScroll,
    jumpToBottom,
    switchSession,
    startPrep,
    setAskDialog,
    deleteSession,
    archiveSession,
    clearSession,
    messageActions,
    compactionActions,
    archiveGroups,
    rateTarget,
    rateBusy,
    closeRate,
    submitRate,
  } = chat;

  // Data is loaded by the hook; the page only renders and forwards events.
  const selectedResume = useMemo(
    () => resumes.find((r) => r.id === resumeId) ?? null,
    [resumes, resumeId],
  );

  // Per-group archived assistant actions, built once per archive change so the
  // memoized bubbles skip re-renders while a live stream updates messages.
  const archiveAssistantActions = useMemo(
    () =>
      archiveGroups.map((g) => ({
        onExport: messageActions.onExport,
        ...(g.backupSessionId !== null && !g.staleBackup
          ? {
              onFork: (target: PrepChatMessage) => {
                if (target.backendIndex === undefined) return;
                compactionActions.onForkFromPoint(g.backupSessionId as number, target.backendIndex);
              },
            }
          : {}),
      })),
    [archiveGroups, messageActions, compactionActions],
  );

  return (
    <div className="page-shell flex h-full min-h-0 flex-col overflow-hidden !pb-4 anim-rise">
      <div className="page-header !mb-4 shrink-0">
        <div className="flex items-start gap-3">
          <span className="icon-badge icon-badge-brand">
            <BookOpen size={18} strokeWidth={1.75} />
          </span>
          <div>
            <p className="page-eyebrow">{t("page.eyebrow")}</p>
            <h1 className="page-title">{t("page.title")}</h1>
          </div>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-5 overflow-hidden lg:grid-cols-[1fr_300px]">
        {/* Main conversation area */}
        <div className="flex min-h-0 flex-col overflow-hidden">
          {switchError && (
            <div className="alert alert-error !mb-3 flex items-center justify-between gap-2">
              <span className="min-w-0 break-words">{switchError}</span>
              <span className="flex shrink-0 items-center gap-2">
                {switchFailedId != null && (
                  <button
                    type="button"
                    onClick={() => {
                      void deleteSession(switchFailedId).then(() => clearSwitchError());
                    }}
                    className="rounded border border-current px-2 py-0.5 text-[12px] font-medium opacity-90 transition-opacity hover:opacity-100"
                  >
                    {t("sessions.delete")}
                  </button>
                )}
                <button
                  type="button"
                  onClick={clearSwitchError}
                  className="shrink-0 text-[16px] leading-none opacity-70 transition-opacity hover:opacity-100"
                  aria-label={t("chat.dismissError")}
                >
                  ×
                </button>
              </span>
            </div>
          )}
          {!prepSessionId ? (
            <PrepEmptyState
              resumeLoadError={resumeLoadError}
              resumes={resumes}
              resumeId={resumeId}
              onResumeChange={setResumeId}
              prepError={prepError}
              starting={starting}
              onStart={startPrep}
            />
          ) : (
            <>
              <div className="relative min-h-0 flex-1">
                <div
                  ref={chatScrollRef}
                  onScroll={handleScroll}
                  className="surface-card h-full overflow-y-auto p-4 [scrollbar-gutter:stable]"
                >
                  <div ref={contentRef} className="space-y-3.5">
                    {archiveGroups.map((g, gi) =>
                      g.messages.map((m) => {
                        // Archived turns stay fully interactive for copy/fork:
                        // fork targets the backup session holding the verbatim
                        // originals. Stale groups (backup retired) keep copy.
                        if (m.role === "assistant") {
                          return (
                            <AssistantBubble
                              key={m.id}
                              msg={m}
                              actions={
                                archiveAssistantActions[gi] ?? {
                                  onExport: (target: PrepChatMessage) =>
                                    messageActions.onExport(target),
                                }
                              }
                            />
                          );
                        }
                        if (m.role === "user") {
                          const forkable =
                            g.backupSessionId !== null && !g.staleBackup
                              ? {
                                  onFork: (target: PrepChatMessage) =>
                                    target.backendIndex !== undefined &&
                                    compactionActions.onForkFromPoint(
                                      g.backupSessionId as number,
                                      target.backendIndex,
                                    ),
                                }
                              : {};
                          return <UserBubble key={m.id} msg={m} actions={{ ...forkable }} />;
                        }
                        return null;
                      }),
                    )}
                    {messages.map((m) =>
                      m.role === "assistant" ? (
                        <AssistantBubble key={m.id} msg={m} actions={messageActions} />
                      ) : m.role === "compaction" ? (
                        <CompactionCard
                          key={m.id}
                          msg={m}
                          sessionId={prepSessionId}
                          actions={compactionActions}
                          disabled={loading || compacting}
                        />
                      ) : (
                        <UserBubble key={m.id} msg={m} actions={messageActions} />
                      ),
                    )}
                  </div>
                </div>
                {showJump && (
                  <button
                    type="button"
                    onClick={jumpToBottom}
                    className="btn-primary absolute bottom-3 right-3 !h-9 !w-9 rounded-full !p-0 shadow-lg"
                    aria-label={t("chat.jumpToBottom")}
                  >
                    <ArrowDown size={15} />
                  </button>
                )}
              </div>
              <PrepComposer
                messages={messages}
                tokenUsage={tokenUsage}
                usage={usage}
                contextBuckets={contextBuckets}
                contextTotal={contextTotal}
                reportedContext={reportedContext}
                estimatedPrompt={estimatedPrompt}
                chatModels={chatModels}
                selectedModelId={selectedModelId}
                onModelChange={setSelectedModelId}
                defaultChatProfile={defaultChatProfile}
                effort={effort}
                onEffortChange={setEffort}
                loading={loading}
                compacting={compacting}
                input={input}
                onInputChange={setInput}
                onSend={handleSend}
                onStop={handleStop}
                onSlashCommand={handleSlashCommand}
                sessions={sessions}
                currentSessionId={prepSessionId}
                pendingRefs={pendingRefs}
                onAddRef={addRef}
                onRemoveRef={removeRef}
              />
            </>
          )}
        </div>

        {/* Context and shortcuts */}
        <PrepSidePanel
          selectedResume={selectedResume}
          sessions={sessions}
          prepSessionId={prepSessionId}
          starting={starting}
          busySids={busySids}
          onSelectSession={switchSession}
          onNewSession={handleNewSession}
          onQuickPrompt={handleQuickPrompt}
          onDeleteSession={(id) => void deleteSession(id)}
          onArchiveSession={(id, archived) => void archiveSession(id, archived)}
          onClearSession={(id) => void clearSession(id)}
          onStopSession={(id) => stopSession(id)}
        />
      </div>

      {askDialog && (
        <AskUserModal
          dialog={askDialog}
          onAnswer={handleAskAnswer}
          onClose={() => setAskDialog(null)}
        />
      )}
      {rateTarget && (
        <RateModal busy={rateBusy} onSubmit={(data) => void submitRate(data)} onClose={closeRate} />
      )}
      <ConfirmDialog
        open={slashClearOpen}
        title={t("sessions.clearTitle")}
        message={t("sessions.clearBody")}
        confirmLabel={t("sessions.clear")}
        cancelLabel={t("sessions.cancelAction")}
        busy={false}
        onConfirm={confirmSlashClear}
        onCancel={cancelSlashClear}
      />
    </div>
  );
}
