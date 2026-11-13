// @vitest-environment jsdom
/**
 * @file useReportLoad.test.tsx
 * @description Live report completion must publish the report before the
 * ledger fallback request settles, or the page renders a transient
 * "report unavailable" branch after the SSE done event.
 */

import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/base";
import type { ReportStreamEvent } from "@/lib/api/reportHttp";
import type { LedgerDocument } from "@/types/domains/records";
import type { DebriefReport } from "@/types/domains/report";

vi.mock("@/lib/api/clients", () => ({
  reportHttp: { getReport: vi.fn(), streamReport: vi.fn() },
  recordsHttp: { getLedger: vi.fn() },
}));

vi.mock("@/i18n/resolve", () => ({
  getTranslator: () => (key: string) => key,
}));

import { recordsHttp, reportHttp } from "@/lib/api/clients";

import { useReportLoad } from "../useReportLoad";

const getReportMock = vi.mocked(reportHttp.getReport);
const streamReportMock = vi.mocked(reportHttp.streamReport);
const getLedgerMock = vi.mocked(recordsHttp.getLedger);

const REPORT = {
  overall_score: 82,
  score_breakdown: {},
  verdict: "passed",
  strengths: ["clear structure"],
  weaknesses: [],
  improvement_suggestions: [],
  training_plan: [],
  turn_notes: [],
} as unknown as DebriefReport;

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  cleanup();
});

describe("useReportLoad live completion", () => {
  it("publishes the report before the ledger fallback resolves", async () => {
    // Fast path: the report is not ready yet, so the hook opens the live stream.
    getReportMock.mockRejectedValue(
      new ApiError("Report not generated yet", 404, { code: "A2004", retryable: true }),
    );

    let emit: ((event: ReportStreamEvent) => void) | null = null;
    streamReportMock.mockImplementation((_id, onEvent) => {
      emit = onEvent;
      return new Promise<void>(() => {
        /* stays open until the component unmounts */
      });
    });

    let resolveLedger!: (ledger: LedgerDocument) => void;
    getLedgerMock.mockImplementation(
      () =>
        new Promise<LedgerDocument>((resolve) => {
          resolveLedger = resolve;
        }),
    );

    const { result } = renderHook(() => useReportLoad(5));
    await waitFor(() => {
      expect(streamReportMock).toHaveBeenCalled();
    });

    await act(async () => {
      emit?.({
        type: "done",
        report: REPORT,
        messages_count: 12,
        duration_minutes: 24,
      });
    });

    // The done event carries no ledger, so the ledger request is still in
    // flight here; the report must already be visible.
    expect(result.current.report).toEqual(REPORT);
    expect(result.current.loading).toBe(false);
    expect(result.current.generating).toBe(false);
    expect(result.current.ledger).toBeNull();

    await act(async () => {
      resolveLedger({ turns: [] } as unknown as LedgerDocument);
    });
    expect(result.current.ledger).not.toBeNull();
  });
});
