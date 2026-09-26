// @vitest-environment jsdom
/**
 * @file useResumeCollection.test.ts
 * @description Poll generation guard: a poll snapshot landing after a manual
 * load must be discarded, while the poll chain keeps converging pending rows.
 */

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useResumeCollection } from "../useResumeCollection";
import { resumeHttp } from "@/lib/api/clients";

import { makeResumeResponse } from "./helpers";

vi.mock("@/lib/api/clients", () => ({
  resumeHttp: { listResumes: vi.fn() },
}));

const listMock = vi.mocked(resumeHttp.listResumes);

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  cleanup();
});

describe("useResumeCollection poll generation guard", () => {
  it("discards a poll snapshot superseded by a manual load", async () => {
    vi.useFakeTimers();
    try {
      const pending = makeResumeResponse({ id: 7, parse_status: "pending" });
      const fresh = makeResumeResponse({ id: 7, parse_status: "done" });
      listMock.mockResolvedValue([pending]);
      const { result } = renderHook(() => useResumeCollection());
      await act(async () => {});
      expect(result.current.resumes[0]?.parse_status).toBe("pending");

      // The poll tick fires while its response is still in flight.
      let resolvePoll!: (v: typeof pending[]) => void;
      listMock.mockImplementationOnce(
        () => new Promise((resolve) => (resolvePoll = resolve)),
      );
      await act(async () => {
        await vi.advanceTimersByTimeAsync(4_000);
      });
      expect(listMock).toHaveBeenCalledTimes(2);

      // A manual load lands fresher data while the poll is pending.
      listMock.mockResolvedValueOnce([fresh]);
      await act(async () => {
        await result.current.load();
      });
      expect(result.current.resumes[0]?.parse_status).toBe("done");

      // The late poll snapshot (older than the manual load) is discarded.
      await act(async () => {
        resolvePoll([pending]);
        await vi.advanceTimersByTimeAsync(0);
      });
      expect(result.current.resumes[0]?.parse_status).toBe("done");
      expect(listMock).toHaveBeenCalledTimes(3);
    } finally {
      vi.useRealTimers();
    }
  });

  it("keeps polling after a superseded tick while rows are still pending", async () => {
    vi.useFakeTimers();
    try {
      const pending = makeResumeResponse({ id: 7, parse_status: "pending" });
      listMock.mockResolvedValue([pending]);
      const { result } = renderHook(() => useResumeCollection());
      await act(async () => {});

      let resolvePoll!: (v: typeof pending[]) => void;
      listMock.mockImplementationOnce(
        () => new Promise((resolve) => (resolvePoll = resolve)),
      );
      await act(async () => {
        await vi.advanceTimersByTimeAsync(4_000);
      });
      expect(listMock).toHaveBeenCalledTimes(2);

      // Manual load during the tick: still pending, so the chain must survive.
      listMock.mockResolvedValueOnce([pending]);
      await act(async () => {
        await result.current.load();
      });

      resolvePoll([pending]);
      await act(async () => {
        await vi.advanceTimersByTimeAsync(0);
      });

      // The next tick fires after another interval: convergence continues.
      await act(async () => {
        await vi.advanceTimersByTimeAsync(4_000);
      });
      expect(listMock).toHaveBeenCalledTimes(4);
      expect(result.current.resumes).toHaveLength(1);
    } finally {
      vi.useRealTimers();
    }
  });
});
