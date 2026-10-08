// @vitest-environment jsdom
/**
 * @file usePrepDeepLink.test.tsx
 * @description One-shot deep-link consumption: resume pairing, catalog wait,
 * failure paths, and StrictMode's effect → cleanup → effect cycle (which
 * must neither cancel the only run nor double-send).
 */

import { StrictMode } from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { parsePrepDeepLink } from "@/features/resume/sendToPrep";
import { usePrepDeepLink } from "../hooks/usePrepDeepLink";

vi.mock("@/i18n/resolve", () => ({
  getTranslator: () => (key: string) => key,
}));

vi.mock("@/components/Toast", () => ({
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() },
}));

const startPrep = vi.fn();
const sendMessage = vi.fn();
const setResumeId = vi.fn();

type HookOpts = Parameters<typeof usePrepDeepLink>[0];

const baseOpts = (over: Partial<HookOpts> = {}): HookOpts => {
  return {
    resumes: [{ id: 7, filename: "cv.pdf", is_active: true }],
    resumesLoaded: true,
    sessionsLoaded: true,
    setResumeId,
    startPrep,
    sendMessage,
    ...over,
  } as HookOpts;
};

const pushLink = (resumeId: number | null, question: string): void => {
  const params = new URLSearchParams();
  if (resumeId != null) params.set("resume", String(resumeId));
  params.set("q", question);
  window.history.replaceState(null, "", `/prep?${params.toString()}`);
};

beforeEach(() => {
  window.history.replaceState(null, "", "/prep");
  vi.clearAllMocks();
  startPrep.mockResolvedValue(42);
  sendMessage.mockResolvedValue(true);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("usePrepDeepLink", () => {
  it("creates a paired session and sends the seeded question", async () => {
    pushLink(7, "drill me");
    renderHook(() => usePrepDeepLink(baseOpts()));
    await waitFor(() => expect(setResumeId).toHaveBeenCalledWith(7));
    await waitFor(() => expect(startPrep).toHaveBeenCalledWith(7));
    await waitFor(() =>
      expect(sendMessage).toHaveBeenCalledWith("drill me", 42, false, { assumeViewing: true }),
    );
    expect(window.location.search).toBe("");
  });

  it("falls back to the current pairing when the resume id is unknown", async () => {
    pushLink(999, "drill me");
    renderHook(() => usePrepDeepLink(baseOpts()));
    await waitFor(() => expect(startPrep.mock.calls[0]).toEqual([undefined]));
    expect(setResumeId).not.toHaveBeenCalled();
    expect(sendMessage).toHaveBeenCalled();
  });

  it("does nothing without a question param", () => {
    window.history.replaceState(null, "", "/prep?resume=7");
    renderHook(() => usePrepDeepLink(baseOpts()));
    expect(startPrep).not.toHaveBeenCalled();
    expect(sendMessage).not.toHaveBeenCalled();
  });

  it("does not send when session creation fails", async () => {
    pushLink(7, "drill me");
    startPrep.mockResolvedValue(null);
    renderHook(() => usePrepDeepLink(baseOpts()));
    await waitFor(() => expect(startPrep).toHaveBeenCalled());
    expect(sendMessage).not.toHaveBeenCalled();
  });

  it("waits for the catalogs before consuming the pairing", async () => {
    pushLink(7, "drill me");
    const { rerender } = renderHook((opts: HookOpts) => usePrepDeepLink(opts), {
      initialProps: baseOpts({ resumes: [], resumesLoaded: false, sessionsLoaded: false }),
    });
    await new Promise((r) => setTimeout(r, 10));
    expect(startPrep).not.toHaveBeenCalled();
    rerender(baseOpts());
    await waitFor(() => expect(startPrep).toHaveBeenCalledWith(7));
    expect(setResumeId).toHaveBeenCalledWith(7);
  });

  it("preserves the linked resume when the catalog wait times out", async () => {
    vi.useFakeTimers();
    pushLink(999, "drill me");
    renderHook(() => usePrepDeepLink(baseOpts({ resumesLoaded: false })));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(9960);
    });
    expect(startPrep).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(120);
    });

    expect(setResumeId).toHaveBeenCalledWith(999);
    expect(startPrep).toHaveBeenCalledExactlyOnceWith(999);
    expect(sendMessage).toHaveBeenCalledWith("drill me", 42, false, { assumeViewing: true });
  });

  it("does not select a resume or start a session after unmounting during the wait", async () => {
    vi.useFakeTimers();
    pushLink(7, "drill me");
    const { unmount } = renderHook(() => usePrepDeepLink(baseOpts({ sessionsLoaded: false })));
    unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_080);
    });

    expect(setResumeId).not.toHaveBeenCalled();
    expect(startPrep).not.toHaveBeenCalled();
    expect(sendMessage).not.toHaveBeenCalled();
  });

  it("keeps waiting through StrictMode cleanup and starts once the catalogs load", async () => {
    vi.useFakeTimers();
    pushLink(7, "drill me");
    const { rerender } = renderHook((opts: HookOpts) => usePrepDeepLink(opts), {
      initialProps: baseOpts({ resumes: [], resumesLoaded: false, sessionsLoaded: false }),
      wrapper: StrictMode,
    });
    expect(startPrep).not.toHaveBeenCalled();
    rerender(baseOpts());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(120);
    });

    expect(startPrep).toHaveBeenCalledExactlyOnceWith(7);
    expect(sendMessage).toHaveBeenCalledTimes(1);
  });

  it("survives StrictMode double-mount without cancelling or double-sending", async () => {
    pushLink(7, "drill me");
    renderHook(() => usePrepDeepLink(baseOpts()), { wrapper: StrictMode });
    await waitFor(() => expect(sendMessage).toHaveBeenCalledTimes(1), { timeout: 3000 });
    expect(startPrep).toHaveBeenCalledTimes(1);
    expect(sendMessage).toHaveBeenCalledWith("drill me", 42, false, { assumeViewing: true });
  });

  it("strips the params immediately, before the catalogs settle", async () => {
    pushLink(7, "drill me");
    const { rerender } = renderHook((opts: HookOpts) => usePrepDeepLink(opts), {
      initialProps: baseOpts({ resumesLoaded: false, sessionsLoaded: false }),
    });
    // Consumed synchronously on mount: a refresh right after cannot re-send.
    expect(parsePrepDeepLink(window.location.search)).toBeNull();
    rerender(baseOpts());
    await waitFor(() => expect(startPrep).toHaveBeenCalled());
  });
});
