/** Interview report REST client (records domain under /v1/reports). */

import type { DebriefReport, GetReportResponse } from "@/types/domains/report";
import {
  ANALYZE_TIMEOUT_MS,
  ApiError,
  consumeSSE,
  request,
  resolveBackendUrl,
} from "@/lib/api/base";
import { getLocale } from "@/i18n/resolve";

/** Live agent event emitted while a report is generating. */
export type ReportStreamEvent = {
  type: "stage" | "tool_step" | "thinking" | "token" | "done" | "error";
  stage?: string;
  batch?: string;
  name?: string;
  status?: string;
  result?: string;
  content?: string;
  message?: string;
  code?: string;
  report?: DebriefReport;
};

export const reportHttp = {
  getReport: (id: number) => request<GetReportResponse>(`/v1/reports/${id}`),

  /** Open the live generation stream; resolves when the stream ends. */
  streamReport: async (
    id: number,
    onEvent: (event: ReportStreamEvent) => void,
  ): Promise<void> => {
    const url = resolveBackendUrl(`/api/v1/reports/${id}/stream`);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), ANALYZE_TIMEOUT_MS);
    let res: Response;
    try {
      res = await fetch(url, {
        method: "GET",
        credentials: "include",
        headers: { "Accept-Language": getLocale() },
        signal: controller.signal,
      });
    } catch {
      clearTimeout(timer);
      throw new ApiError("Cannot reach the backend", 0, { code: "NET0000" });
    }
    if (!res.ok) {
      clearTimeout(timer);
      throw new ApiError("Report stream unavailable", res.status, { code: "NET0005" });
    }
    try {
      await consumeSSE<ReportStreamEvent>(res, onEvent);
    } finally {
      clearTimeout(timer);
    }
  },
};
