/**
 * Records domain REST client: history sessions, ledger replay, report retry.
 * Paths match domains/records routers mounted under /api/v1.
 */

import type { GetReportResponse } from "@/types/domains/report";
import type { LedgerDocument, SessionHistoryItem } from "@/types/domains/records";
import { request, LLM_HEAVY_TIMEOUT_MS } from "@/lib/api/base";

export const recordsHttp = {
  listSessions: () => request<SessionHistoryItem[]>(`/v1/records/sessions`),
  getLedger: (id: number) =>
    request<LedgerDocument>(`/v1/records/sessions/${id}/ledger`),
  retryReport: (id: number) =>
    request<GetReportResponse>(`/v1/reports/${id}/retry`, {
      method: "POST",
      timeoutMs: LLM_HEAVY_TIMEOUT_MS,
    }),
};
