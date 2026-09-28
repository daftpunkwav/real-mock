/**
 * @file waitForStoppedPersist.test.ts
 * @description Stopped-persist confirmation: applies the length only after two
 * consecutive equal reads, exits fast on transport errors, and stops polling
 * when the caller's shouldContinue gate closes.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { prepCoachHttp as api } from "@/lib/api/clients";

import { waitForStoppedPersist } from "../hooks/waitForStoppedPersist";

vi.mock("@/lib/api/clients", () => ({
  prepCoachHttp: {
    prepMessages: vi.fn(),
  },
}));

const prepMessagesMock = vi.mocked(api.prepMessages);

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("waitForStoppedPersist", () => {
  it("applies the count after two consecutive equal reads", async () => {
    const list = [{ role: "user" }, { role: "assistant" }, { role: "assistant" }];
    prepMessagesMock.mockResolvedValue(list as never);
    const applyCount = vi.fn();

    const done = waitForStoppedPersist(7, applyCount);
    await vi.advanceTimersByTimeAsync(600);
    await done;

    expect(applyCount).toHaveBeenCalledWith(7, 3);
    expect(prepMessagesMock).toHaveBeenCalledTimes(2);
  });

  it("keeps polling while the count changes, then settles", async () => {
    prepMessagesMock
      .mockResolvedValueOnce([{ role: "user" }] as never)
      .mockResolvedValueOnce([{ role: "user" }, { role: "assistant" }] as never)
      .mockResolvedValue([{ role: "user" }, { role: "assistant" }] as never);
    const applyCount = vi.fn();

    const done = waitForStoppedPersist(7, applyCount);
    await vi.advanceTimersByTimeAsync(1200);
    await done;

    expect(applyCount).toHaveBeenCalledWith(7, 2);
    expect(prepMessagesMock).toHaveBeenCalledTimes(3);
  });

  it("exits fast on a transport error without applying", async () => {
    prepMessagesMock.mockRejectedValue(new Error("down"));
    const applyCount = vi.fn();

    const done = waitForStoppedPersist(7, applyCount);
    await vi.advanceTimersByTimeAsync(100);
    await done;

    expect(applyCount).not.toHaveBeenCalled();
    expect(prepMessagesMock).toHaveBeenCalledTimes(1);
  });

  it("returns without requesting when shouldContinue is already false", async () => {
    prepMessagesMock.mockResolvedValue([] as never);
    const applyCount = vi.fn();

    const done = waitForStoppedPersist(7, applyCount, () => false);
    await vi.advanceTimersByTimeAsync(100);
    await done;

    expect(prepMessagesMock).not.toHaveBeenCalled();
    expect(applyCount).not.toHaveBeenCalled();
  });
});
