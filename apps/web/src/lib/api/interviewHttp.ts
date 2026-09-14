/** Mock interview REST client. */

import type {
  ChatMessage,
  FinishInterviewResponse,
  InterviewConfig,
  InterviewProcessResponse,
  InterviewSession,
  Options,
  ProcessCreateRequest,
  ProcessCreatedResponse,
  ResumePickerItem,
} from "@/lib/api/contract";
import type { ReasoningEffort } from "@/types";
import { request, LLM_HEAVY_TIMEOUT_MS } from "@/lib/api/base";

export const interviewHttp = {
  getOptions: () => request<Options>("/v1/options"),
  listResumes: () => request<ResumePickerItem[]>("/v1/interview/resumes"),

  createSessionWithAI: (
    config: InterviewConfig,
    ai?: {
      chat_profile_id?: number | null;
      stt_profile_id?: number | null;
      tts_profile_id?: number | null;
      reasoning_effort?: ReasoningEffort | null;
    } | null,
  ) =>
    request<InterviewSession>("/v1/interview/sessions", {
      method: "POST",
      body: JSON.stringify({ ...config, ai_overrides: ai ?? undefined }),
    }),
  listSessions: () => request<InterviewSession[]>("/v1/interview/sessions"),
  getSession: (id: number) => request<InterviewSession>(`/v1/interview/sessions/${id}`),
  getMessages: (id: number) => request<ChatMessage[]>(`/v1/interview/sessions/${id}/messages`),
  finishInterview: (id: number) =>
    request<FinishInterviewResponse>(`/v1/interview/sessions/${id}/finish`, {
      method: "POST",
      timeoutMs: LLM_HEAVY_TIMEOUT_MS,
    }),

  // Multi-round interview processes (round 1..5)
  listProcesses: () => request<InterviewProcessResponse[]>("/v1/interview/processes"),
  createProcess: (config: ProcessCreateRequest) =>
    request<ProcessCreatedResponse>("/v1/interview/processes", {
      method: "POST",
      body: JSON.stringify(config),
    }),
  createNextRound: (processId: number) =>
    request<InterviewSession>(`/v1/interview/processes/${processId}/rounds`, {
      method: "POST",
    }),
};
