/**
 * Records domain REST client: history sessions, ledger replay, report retry.
 * Paths match domains/records routers mounted under /api/v1.
 */

import type { DataExportFile } from "@/lib/api/contract";
import type { GetReportResponse } from "@/types/domains/report";
import type { LedgerDocument, SessionHistoryItem } from "@/types/domains/records";
import { request, LLM_HEAVY_TIMEOUT_MS } from "@/lib/api/base";

export const recordsHttp = {
  listSessions: () => request<SessionHistoryItem[]>(`/v1/records/sessions`),
  getLedger: (id: number) => request<LedgerDocument>(`/v1/records/sessions/${id}/ledger`),
  retryReport: (id: number) =>
    request<GetReportResponse>(`/v1/reports/${id}/retry`, {
      method: "POST",
      timeoutMs: LLM_HEAVY_TIMEOUT_MS,
    }),
  /** Download one session's debrief report (md / json) as a file payload. */
  exportReport: (id: number, format: "md" | "json") =>
    request<DataExportFile>(`/v1/records/export/report/${id}?format=${format}`, {
      timeoutMs: LLM_HEAVY_TIMEOUT_MS,
    }),
  /** Download one session's plain interviewer/candidate transcript. */
  exportRecord: (id: number, format: "md" | "json") =>
    request<DataExportFile>(`/v1/records/export/record/${id}?format=${format}`, {
      timeoutMs: LLM_HEAVY_TIMEOUT_MS,
    }),
};
