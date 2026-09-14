/**
 * @file index.ts
 * @description Prep feature barrel: chat UI, send pipeline, and shared prep
 * utilities. Hooks other than usePrepChat and the stream registry stay
 * private to the feature; import them via relative paths inside prep.
 */

export { AskUserModal } from "./components/AskUserModal";
export { PrepComposer } from "./components/PrepComposer";
export { PrepEmptyState } from "./components/PrepEmptyState";
export { PrepSessionList } from "./components/PrepSessionList";
export { PrepSidePanel } from "./components/PrepSidePanel";
export { RateModal, type RateSubmit } from "./components/RateModal";
export { SearchResultCards } from "./components/SearchResultCards";
export { ThinkAnswerMessage } from "./components/ThinkAnswerMessage";
export { TraceTimeline } from "./components/TraceTimeline";
export { AssistantBubble, UserBubble } from "./components/ChatBubbles";
export { CompactionCard, type CompactionCardActions } from "./components/CompactionCard";
export { usePrepChat } from "./hooks/usePrepChat";
export type { PrepChatMessage, PrepCompactionCard, PrepStreamHandlers, PrepStreamOptions, PrepTraceItem } from "./types";
export type { PrepSendSnapshot } from "./hooks/usePrepSend";
export {
  appendTraceThinking,
  appendTraceTool,
  buildTraceFromParts,
  mapHistoryMessages,
  normalizeSearchGroups,
  normalizeSteps,
  normalizeThinking,
  parseSummaryBlock,
} from "./history";
export { resolveSelectedModel } from "./modelChoice";
export { estimatePrepContext, assistantMetaChars, estimateTextTokens } from "./contextEstimate";
export type { PrepContextEstimate } from "./contextEstimate";
export { matchSlashCommands, parseCompactArgs, parseSlashCommand, resolveSlashCommand, SLASH_NAMES } from "./slashCommands";
export type { SlashName } from "./slashCommands";
export { detectHashQuery, refCandidates, refLabel, stripHashQuery } from "./sessionRefs";
export type { PendingSessionRef } from "./sessionRefs";
export {
  STREAM_STOP_GRACE_MS,
  abortStream,
  activeStreamIds,
  completeStream,
  hasActiveStream,
  registerStream,
  subscribeStreams,
} from "./streamRegistry";
