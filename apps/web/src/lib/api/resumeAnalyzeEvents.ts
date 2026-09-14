/**
 * @file resumeAnalyzeEvents.ts
 * @description SSE event contract for POST /v1/resume/{id}/analyze/stream.
 */

import type { ResumeAnalysis } from "@/lib/api/contract";

export type ReviewPlanStatus = "pending" | "in_progress" | "done" | "skipped";

export interface ReviewPlanStep {
  id: string;
  title: string;
  status: ReviewPlanStatus | string;
  note?: string;
  /** "parallel" = independent evidence, batched with peers; absent means serial. */
  mode?: string;
}

export type ReviewToolStatus = "running" | "done" | "error";

export type ResumeAnalyzeSSEEvent =
  | { type: "plan"; steps: ReviewPlanStep[] }
  | {
      type: "tool_step";
      id?: string;
      name: string;
      query?: string;
      status?: ReviewToolStatus | string;
      args?: Record<string, unknown>;
      result?: string;
      sites?: string[];
    }
  | { type: "thinking"; content: string }
  | { type: "notice"; kind?: string; message?: string }
  | { type: "done"; analysis: ResumeAnalysis }
  | { type: "error"; message?: string; code?: string; retryable?: boolean };
