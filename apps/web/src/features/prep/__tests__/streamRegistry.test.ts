// @vitest-environment jsdom
/** Stream registry: per-session abort tracking. */

import { afterEach, describe, expect, it } from "vitest";

import {
  abortStream,
  activeStreamIds,
  clearStreamsForTests,
  completeStream,
  hasActiveStream,
  registerStream,
  subscribeStreams,
} from "../streamRegistry";

afterEach(() => {
  clearStreamsForTests();
});

describe("streamRegistry", () => {
  it("tracks one controller per session", () => {
    expect(hasActiveStream(1)).toBe(false);
    const first = new AbortController();
    registerStream(1, first);
    expect(hasActiveStream(1)).toBe(true);
    expect(hasActiveStream(2)).toBe(false);
    registerStream(1, new AbortController());
    expect(hasActiveStream(1)).toBe(true);
    expect(completeStream(1)).toBe(true);
    expect(hasActiveStream(1)).toBe(false);
    expect(completeStream(1)).toBe(false);
  });

  it("aborts and forgets the controller", () => {
    const onAbort = new Promise<void>((resolve) => {
      const controller = new AbortController();
      controller.signal.addEventListener("abort", () => resolve());
      registerStream(7, controller);
    });
    expect(abortStream(7)).toBe(true);
    expect(hasActiveStream(7)).toBe(false);
    expect(abortStream(7)).toBe(false);
    return onAbort;
  });

  it("notifies subscribers with the active id snapshot", () => {
    const seen: number[][] = [];
    const unsubscribe = subscribeStreams((ids) => seen.push(ids));
    registerStream(1, new AbortController());
    registerStream(2, new AbortController());
    expect(activeStreamIds().sort()).toEqual([1, 2]);
    completeStream(1);
    abortStream(2);
    unsubscribe();
    // No notifications after unsubscribe.
    registerStream(3, new AbortController());
    expect(seen).toEqual([[1], [1, 2], [2], []]);
  });
});
