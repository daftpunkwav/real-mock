// @vitest-environment jsdom
/**
 * @file usePrepMessageActions.test.ts
 * @description Regression lock for handleRetract: the A3003 stale-count guard
 * resyncs from the backend and retries the truncate exactly once before
 * reporting; other failures report immediately.
 */

import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { usePrepMessageActions } from "../hooks/usePrepMessageActions";
import { prepCoachHttp as api } from "@/lib/api/clients";
import { ApiError } from "@/lib/api/base";
import type { PrepChatMessage } from "../types";

vi.mock("@/lib/api/clients", () => ({
  prepCoachHttp: {
    prepMessages: vi.fn(),
    truncateMessages: vi.fn(),
    forkSession: vi.fn(),
  },
}));

vi.mock("@/lib/api/prepMemoryHttp", () => ({
  prepMemoryHttp: { createFromRating: vi.fn() },
}));

const toastError = vi.hoisted(() => vi.fn());
vi.mock("@/components/Toast", () => ({
  toast: { error: toastError, success: vi.fn() },
}));

const prepMessagesMock = vi.mocked(api.prepMessages);
const truncateMock = vi.mocked(api.truncateMessages);

function makeMsg(overrides: Partial<PrepChatMessage> = {}): PrepChatMessage {
  return { id: "u1", role: "user", content: "question", ...overrides };
}

type HookOptions = Parameters<typeof usePrepMessageActions>[0];

function makeOptions(overrides: Partial<HookOptions> = {}) {
  // Mirrors the session hook: setBackendCount feeds the tracked count that
  // truncate reads as its optimistic-concurrency guard.
  let count = 2;
  return {
    prepSessionId: 7 as number | null,
    messages: [
      makeMsg({ backendIndex: 1 }),
      makeMsg({ id: "a1", role: "assistant", content: "answer", backendIndex: 2 }),
    ],
    setMessages: vi.fn(),
    stopStream: vi.fn(),
    sendMessage: vi.fn(async () => true),
    switchSession: vi.fn(async () => undefined),
    setBackendCount: vi.fn((_sid: number, n: number) => {
      count = n;
    }),
    backendCount: () => count,
    refreshSessions: vi.fn(),
    ...overrides,
  } as HookOptions;
}

function renderActions(options: HookOptions) {
  return renderHook((opts: HookOptions) => usePrepMessageActions(opts), {
    initialProps: options,
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  cleanup();
});

describe("usePrepMessageActions.handleRetract", () => {
  it("resyncs once on A3003 and retries the truncate with the fresh count", async () => {
    // waitForStoppedPersist exits fast on transport errors (catch-and-return).
    prepMessagesMock
      .mockRejectedValueOnce(new Error("skip persist wait"))
      .mockResolvedValueOnce([
        { role: "user", content: "q" },
        { role: "assistant", content: "a" },
        { role: "assistant", content: "extra" },
      ] as never)
      .mockRejectedValueOnce(new Error("skip persist wait"));
    truncateMock
      .mockRejectedValueOnce(new ApiError("stale count", 409, { code: "A3003" }))
      .mockResolvedValueOnce({ message_count: 1 });

    const options = makeOptions();
    const { result } = renderActions(options);

    await act(async () => {
      await result.current.handleRetract(options.messages[0]!);
    });

    expect(truncateMock).toHaveBeenCalledTimes(2);
    expect(truncateMock).toHaveBeenNthCalledWith(1, 7, 1, 2);
    expect(truncateMock).toHaveBeenNthCalledWith(2, 7, 1, 3);
    expect(options.stopStream).toHaveBeenCalledTimes(2);
    expect(options.setBackendCount).toHaveBeenCalledWith(7, 3);
    expect(options.refreshSessions).toHaveBeenCalledTimes(1);
    expect(toastError).not.toHaveBeenCalled();

    // The local list is cut before the retracted turn.
    const updater = vi.mocked(options.setMessages).mock.calls.at(-1)![0] as (
      m: PrepChatMessage[],
    ) => PrepChatMessage[];
    expect(updater(options.messages)).toEqual([]);
  });

  it("reports after one retry when the count goes stale again", async () => {
    prepMessagesMock.mockRejectedValue(new Error("skip persist wait"));
    truncateMock
      .mockRejectedValueOnce(new ApiError("stale", 409, { code: "A3003" }))
      .mockRejectedValueOnce(new ApiError("stale again", 409, { code: "A3003" }));

    const options = makeOptions();
    const { result } = renderActions(options);

    await act(async () => {
      await result.current.handleRetract(options.messages[0]!);
    });

    expect(truncateMock).toHaveBeenCalledTimes(2);
    expect(toastError).toHaveBeenCalledTimes(1);
    expect(options.setMessages).not.toHaveBeenCalled();
    expect(options.refreshSessions).not.toHaveBeenCalled();
  });

  it("reports non-A3003 failures immediately without resync or retry", async () => {
    prepMessagesMock.mockRejectedValue(new Error("skip persist wait"));
    truncateMock.mockRejectedValueOnce(new ApiError("boom", 500, { code: "A1006" }));

    const options = makeOptions();
    const { result } = renderActions(options);

    await act(async () => {
      await result.current.handleRetract(options.messages[0]!);
    });

    expect(truncateMock).toHaveBeenCalledTimes(1);
    expect(prepMessagesMock).toHaveBeenCalledTimes(1);
    expect(toastError).toHaveBeenCalledTimes(1);
    expect(options.setMessages).not.toHaveBeenCalled();
  });

  it("does nothing without a session or a backend index", async () => {
    prepMessagesMock.mockRejectedValue(new Error("should not be called"));
    truncateMock.mockRejectedValue(new Error("should not be called"));

    const noSession = makeOptions({ prepSessionId: null });
    const first = renderActions(noSession);
    await act(async () => {
      await first.result.current.handleRetract(noSession.messages[0]!);
    });

    const noIndex = makeOptions();
    const second = renderActions(noIndex);
    await act(async () => {
      await second.result.current.handleRetract(makeMsg());
    });

    expect(truncateMock).not.toHaveBeenCalled();
    expect(prepMessagesMock).not.toHaveBeenCalled();
  });
});
