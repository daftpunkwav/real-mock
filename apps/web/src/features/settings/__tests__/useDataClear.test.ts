// @vitest-environment jsdom
/**
 * @file useDataClear.test.ts
 * @description Contract tests for the settings data-clear hook.
 */

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { resumeHttp } from "@/lib/api/clients";

import { useDataClear } from "../useDataClear";

vi.mock("@/lib/api/clients", () => ({
  resumeHttp: {
    clearReviewResults: vi.fn(),
    clearAllResumes: vi.fn(),
  },
}));

const clearResultsMock = vi.mocked(resumeHttp.clearReviewResults);
const clearAllMock = vi.mocked(resumeHttp.clearAllResumes);

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("useDataClear", () => {
  it("returns the cleared count for review results", async () => {
    clearResultsMock.mockResolvedValue({ ok: true, cleared: 3 });
    const { result } = renderHook(() => useDataClear());
    let count = -1;
    await act(async () => {
      count = await result.current.run("results");
    });
    expect(count).toBe(3);
    expect(clearResultsMock).toHaveBeenCalledTimes(1);
    expect(result.current.busy).toBeNull();
  });

  it("returns the deleted count for the full collection", async () => {
    clearAllMock.mockResolvedValue({ ok: true, deleted: 2 });
    const { result } = renderHook(() => useDataClear());
    let count = -1;
    await act(async () => {
      count = await result.current.run("collection");
    });
    expect(count).toBe(2);
    expect(clearAllMock).toHaveBeenCalledTimes(1);
    expect(result.current.busy).toBeNull();
  });

  it("marks busy while in flight and resets after failure", async () => {
    let release!: () => void;
    const gate = new Promise<{ ok: boolean; cleared: number }>((res) => {
      release = () => res({ ok: true, cleared: 1 });
    });
    clearResultsMock.mockReturnValue(gate);
    const { result } = renderHook(() => useDataClear());
    let pending: Promise<number>;
    act(() => {
      pending = result.current.run("results");
    });
    expect(result.current.busy).toBe("results");
    await act(async () => {
      release();
      await pending;
    });
    expect(result.current.busy).toBeNull();

    clearAllMock.mockRejectedValueOnce(new Error("boom"));
    await expect(
      act(async () => {
        await result.current.run("collection");
      }),
    ).rejects.toThrow("boom");
    expect(result.current.busy).toBeNull();
  });
});
