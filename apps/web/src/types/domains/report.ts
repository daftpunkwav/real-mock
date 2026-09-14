/**
 * Report domain types beyond the OpenAPI-generated InterviewReport contract.
 * Includes debrief turn_notes, report status, and optional ledger on GET.
 */

import type { InterviewReport, ScoreBreakdown } from "@/lib/api/contract";
import type { LedgerDocument } from "@/types/domains/records";

export type { InterviewReport, ScoreBreakdown };

export type ReportStatus = "pending" | "ready" | "failed" | "generating";

export type TurnNoteUserReview = {
  summary?: string;
  suggestions?: string[];
};

export type TurnNoteInterviewerReview = {
  intent?: string;
  quality?: string;
  notes?: string;
};

export type TurnNote = {
  turn_id: string;
  phase?: string;
  /** Interviewer question in this turn. */
  question?: string;
  /** Why the interviewer asked this. */
  question_intent?: string;
  /** One-two sentence summary of the candidate reply. */
  answer_summary?: string;
  /** 0-100; 0 = not rated. */
  score?: number;
  problems?: string[];
  reference_answer?: string;
  how_to_answer?: string;
  knowledge_points?: string[];
  knowledge_brushup?: string;
  exercises?: string[];
  followup_quality?: string;
  user_review?: TurnNoteUserReview;
  interviewer_review?: TurnNoteInterviewerReview;
};

/** Deep debrief payload: legacy InterviewReport fields plus round lineage. */
export type DebriefReport = InterviewReport & {
  turn_notes?: TurnNote[];
  /** passed | failed | null (not judged). */
  verdict?: string | null;
  verdict_reasoning?: string;
  highlights?: string[];
  key_problems?: string[];
  rounds_context?: string;
};

/** Extended GET /v1/reports/{id} response from the records domain. */
export type GetReportResponse = {
  session_id: number;
  report: DebriefReport;
  messages_count: number;
  duration_minutes?: number | null;
  status?: ReportStatus;
  ledger?: LedgerDocument | null;
};
