// @vitest-environment jsdom
/**
 * @file usePrepChatSession.test.ts
 * @description Tests for usePrepChatSession: session restore, switching,
 * creation, race handling, and backend-outage retries.
 */

import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { usePrepChatSession } from "../hooks/usePrepChatSession";
import { prepCoachHttp as api } from "@/lib/api/clients";
import { ApiError } from "@/lib/api/base";

vi.mock("@/lib/api/clients", () => ({
  prepCoachHttp: {
    prepMessages: vi.fn(),
    listPrepSessions: vi.fn(),
    createPrepSession: vi.fn(),
  },
}));

const RESTORE_KEY = "realmock_prep_session_id";
const mockedPrepMessages = vi.mocked(api.prepMessages);
const mockedCreatePrepSession = vi.mocked(api.createPrepSession);

const nextId = (prefix: string) => `${prefix}-1`;

function makeOptions(overrides: Partial<Parameters<typeof usePrepChatSession>[0]> = {}) {
  return {
    setMessages: vi.fn(),
    setAskDialog: vi.fn(),
    nextMsgId: nextId,
    sessions: [],
    resumeId: null,
    refreshSessions: vi.fn(),
    syncBackendCount: vi.fn(),
    setBackendCount: vi.fn(),
    ...overrides,
  };
}

type HookOptions = ReturnType<typeof makeOptions>;

function renderSessionHook(options: HookOptions) {
  return renderHook((opts: HookOptions) => usePrepChatSession(opts), {
    initialProps: options,
  });
}

beforeEach(() => {
  window.localStorage.clear();
  vi.clearAllMocks();
});

afterEach(() => {
  window.localStorage.clear();
});

describe("usePrepChatSession.switchSession", () => {
  it("loads messages and persists the chosen session", async () => {
    mockedPrepMessages.mockResolvedValue([
      { role: "user", content: "hello" },
      { role: "assistant", content: "hi" },
    ] as never);
    const options = makeOptions();
    const { result } = renderSessionHook(options);

    await act(async () => {
      await result.current.switchSession(7);
    });

    expect(mockedPrepMessages).toHaveBeenCalledWith(7);
    expect(options.setMessages).toHaveBeenCalled();
    expect(result.current.prepSessionId).toBe(7);
    expect(result.current.switchError).toBe("");
    expect(window.localStorage.getItem(RESTORE_KEY)).toBe("7");
    expect(result.current.restoring).toBe(false);
  });

  it("clears session state when history load fails", async () => {
    mockedPrepMessages.mockRejectedValue(new Error("load failed"));
    const { result } = renderSessionHook(makeOptions());

    await act(async () => {
      await result.current.switchSession(7);
    });

    expect(result.current.prepSessionId).toBeNull();
    expect(result.current.switchError).toContain("load failed");
    expect(window.localStorage.getItem(RESTORE_KEY)).toBeNull();
  });

  it("keeps the fallback session when explicit switch fails", async () => {
    mockedCreatePrepSession.mockResolvedValue({ id: 5 } as never);
    mockedPrepMessages.mockRejectedValue(new Error("switch failed"));
    const { result } = renderSessionHook(makeOptions());

    await act(async () => {
      await result.current.startPrep();
    });
    expect(window.localStorage.getItem(RESTORE_KEY)).toBe("5");

    await act(async () => {
      await result.current.switchSession(7);
    });

    expect(result.current.prepSessionId).toBe(5);
    expect(result.current.switchError).toContain("switch failed");
    expect(window.localStorage.getItem(RESTORE_KEY)).toBe("5");
  });

  it("ignores empty history without replacing messages", async () => {
    mockedCreatePrepSession.mockResolvedValue({ id: 5 } as never);
    mockedPrepMessages.mockResolvedValue([] as never);
    const options = makeOptions();
    const { result } = renderSessionHook(options);

    await act(async () => {
      await result.current.startPrep();
    });
    vi.mocked(options.setMessages).mockClear();

    await act(async () => {
      await result.current.switchSession(7);
    });

    expect(result.current.prepSessionId).toBe(5);
    expect(result.current.switchError).toBe("");
    expect(options.setMessages).not.toHaveBeenCalled();
    expect(window.localStorage.getItem(RESTORE_KEY)).toBe("5");
  });

  it("lets the newest switch win when switches overlap", async () => {
    let resolveFirst!: (v: never) => void;
    mockedPrepMessages.mockImplementationOnce(
      () => new Promise((resolve) => (resolveFirst = resolve)),
    );
    mockedPrepMessages.mockResolvedValue([
      { role: "user", content: "fresh" },
    ] as never);
    const { result } = renderSessionHook(makeOptions());

    let first!: Promise<void>;
    act(() => {
      first = result.current.switchSession(3);
    });
    await act(async () => {
      await result.current.switchSession(4);
    });
    resolveFirst([{ role: "user", content: "stale" }] as never);
    await act(async () => {
      await first;
    });

    expect(mockedPrepMessages).toHaveBeenCalledTimes(2);
    expect(mockedPrepMessages).toHaveBeenNthCalledWith(1, 3);
    expect(mockedPrepMessages).toHaveBeenNthCalledWith(2, 4);
    expect(result.current.prepSessionId).toBe(4);
  });

  it("switches sessions without blocking on generation", async () => {
    mockedPrepMessages.mockResolvedValue([
      { role: "user", content: "hello" },
    ] as never);
    const { result } = renderSessionHook(makeOptions());

    await act(async () => {
      await result.current.switchSession(7);
    });

    expect(mockedPrepMessages).toHaveBeenCalledWith(7);
    expect(result.current.prepSessionId).toBe(7);
  });

  it("retries history load once on transport failure", async () => {
    mockedPrepMessages
      .mockRejectedValueOnce(new ApiError("unreachable", 0, { code: "NET0000" }))
      .mockResolvedValueOnce([{ role: "user", content: "hello" }] as never);
    const { result } = renderSessionHook(makeOptions());

    await act(async () => {
      await result.current.switchSession(7);
    });

    expect(mockedPrepMessages).toHaveBeenCalledTimes(2);
    expect(result.current.prepSessionId).toBe(7);
  }, 10000);

  it("reports backend outage distinctly when retry and probe both fail", async () => {
    mockedPrepMessages.mockRejectedValue(new ApiError("unreachable", 0, { code: "NET0000" }));
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));
    try {
      const { result } = renderSessionHook(makeOptions());

      await act(async () => {
        await result.current.switchSession(7);
      });

      expect(result.current.prepSessionId).toBeNull();
      expect(result.current.switchError).toContain("Backend is not responding");
    } finally {
      vi.unstubAllGlobals();
    }
  }, 15000);
});

describe("usePrepChatSession.restore", () => {
  it("restores the persisted session on mount", async () => {
    window.localStorage.setItem(RESTORE_KEY, "9");
    mockedPrepMessages.mockResolvedValue([
      { role: "user", content: "hello" },
    ] as never);
    const options = makeOptions();
    renderSessionHook(options);

    await waitFor(() => {
      expect(options.setMessages).toHaveBeenCalled();
    });
    expect(mockedPrepMessages).toHaveBeenCalledWith(9);
  });

  it("clears invalid stored session on load failure", async () => {
    window.localStorage.setItem(RESTORE_KEY, "9");
    mockedPrepMessages.mockRejectedValue(new Error("load failed"));
    const { result } = renderSessionHook(makeOptions());

    await waitFor(() => {
      expect(window.localStorage.getItem(RESTORE_KEY)).toBeNull();
    });
    expect(result.current.prepSessionId).toBeNull();
    expect(result.current.restoring).toBe(false);
  });

  it("clears stored session when backend returns empty history", async () => {
    window.localStorage.setItem(RESTORE_KEY, "9");
    mockedPrepMessages.mockResolvedValue([] as never);
    const { result } = renderSessionHook(makeOptions());

    await waitFor(() => {
      expect(window.localStorage.getItem(RESTORE_KEY)).toBeNull();
    });
    expect(result.current.prepSessionId).toBeNull();
  });
});

describe("usePrepChatSession.startPrep", () => {
  it("creates a new session and seeds a welcome message", async () => {
    mockedCreatePrepSession.mockResolvedValue({ id: 11 } as never);
    const options = makeOptions();
    const { result } = renderSessionHook(options);

    let created: number | null = null;
    await act(async () => {
      created = await result.current.startPrep();
    });

    expect(created).toBe(11);
    expect(result.current.prepSessionId).toBe(11);
    expect(window.localStorage.getItem(RESTORE_KEY)).toBe("11");
    expect(options.setMessages).toHaveBeenCalledWith([
      expect.objectContaining({ role: "assistant" }),
    ]);
  });

  it("surfaces creation errors without persisting a session", async () => {
    mockedCreatePrepSession.mockRejectedValue(new Error("creation failed"));
    const { result } = renderSessionHook(makeOptions());

    let created: number | null = null;
    await act(async () => {
      created = await result.current.startPrep();
    });

    expect(created).toBeNull();
    expect(result.current.prepError).toContain("creation failed");
    expect(window.localStorage.getItem(RESTORE_KEY)).toBeNull();
  });
});
