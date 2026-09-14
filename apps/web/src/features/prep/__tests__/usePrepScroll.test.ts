// @vitest-environment jsdom
/**
 * Right hook
 * Use , .
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { usePrepScroll } from "../hooks/usePrepScroll";

type ObserverCallback = (entries: unknown[], observer: unknown) => void;

class MockResizeObserver {
  static instances: MockResizeObserver[] = [];

  callback: ObserverCallback;
  observed: Element[] = [];

  constructor(callback: ObserverCallback) {
    this.callback = callback;
    MockResizeObserver.instances.push(this);
  }

  observe(el: Element) {
    this.observed.push(el);
  }

  disconnect() {
    this.observed = [];
  }

  unobserve() {}
}

function stubResizeObserver() {
  MockResizeObserver.instances = [];
  vi.stubGlobal("ResizeObserver", MockResizeObserver);
  return () => vi.unstubAllGlobals();
}

/** in */
function withLayout(el: HTMLElement, size: { scrollHeight: number; clientHeight: number }) {
  Object.defineProperty(el, "scrollHeight", {
    value: size.scrollHeight,
    configurable: true,
  });
  Object.defineProperty(el, "clientHeight", {
    value: size.clientHeight,
    configurable: true,
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("usePrepScroll", () => {
  it("auto-scrolls to bottom on content resize", () => {
    const restore = stubResizeObserver();
    const { result, rerender } = renderHook(
      ({ n }) => usePrepScroll(n),
      { initialProps: { n: 0 } },
    );

    const scrollEl = document.createElement("div");
    const contentEl = document.createElement("div");
    withLayout(scrollEl, { scrollHeight: 900, clientHeight: 400 });
    result.current.chatScrollRef.current = scrollEl;
    result.current.contentRef.current = contentEl;

    rerender({ n: 1 });

    expect(MockResizeObserver.instances).toHaveLength(1);
    const observer = MockResizeObserver.instances[0]!;
    expect(observer.observed).toContain(contentEl);

    withLayout(scrollEl, { scrollHeight: 1400, clientHeight: 400 });
    act(() => {
      observer.callback([], observer);
    });
    expect(scrollEl.scrollTop).toBe(1400);
    restore();
  });

  it("shows jump button when user scrolls up and pauses auto-scroll", () => {
    const restore = stubResizeObserver();
    const { result, rerender } = renderHook(
      ({ n }) => usePrepScroll(n),
      { initialProps: { n: 0 } },
    );

    const scrollEl = document.createElement("div");
    withLayout(scrollEl, { scrollHeight: 1400, clientHeight: 400 });
    result.current.chatScrollRef.current = scrollEl;
    result.current.contentRef.current = document.createElement("div");
    rerender({ n: 1 });

    // Note
    act(() => {
      result.current.handleScroll();
    });
    expect(result.current.showJump).toBe(true);

    withLayout(scrollEl, { scrollHeight: 2000, clientHeight: 400 });
    const observerNoPull = MockResizeObserver.instances[0]!;
    act(() => {
      observerNoPull.callback([], observerNoPull);
    });
    expect(scrollEl.scrollTop).toBe(0);
    restore();
  });

  it("stickToBottom", () => {
    const restore = stubResizeObserver();
    const { result, rerender } = renderHook(
      ({ n }) => usePrepScroll(n),
      { initialProps: { n: 0 } },
    );

    const scrollEl = document.createElement("div");
    withLayout(scrollEl, { scrollHeight: 1400, clientHeight: 400 });
    result.current.chatScrollRef.current = scrollEl;
    result.current.contentRef.current = document.createElement("div");
    rerender({ n: 1 });

    act(() => {
      result.current.handleScroll();
    });
    expect(result.current.showJump).toBe(true);

    act(() => {
      result.current.stickToBottom();
    });
    expect(result.current.showJump).toBe(false);

    withLayout(scrollEl, { scrollHeight: 1800, clientHeight: 400 });
    const observerRestored = MockResizeObserver.instances[0]!;
    act(() => {
      observerRestored.callback([], observerRestored);
    });
    expect(scrollEl.scrollTop).toBe(1800);
    restore();
  });

  it("ResizeObserver", () => {
    const { result } = renderHook(({ n }) => usePrepScroll(n), {
      initialProps: { n: 1 },
    });
    expect(result.current.showJump).toBe(false);
  });
});
