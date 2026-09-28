// @vitest-environment jsdom
/**
 * Monotonic width: grows with content, never shrinks back.
 *
 * NOTE: tsconfig uses jsx=preserve (Next.js), which vitest cannot transform —
 * this file avoids JSX syntax via createElement (same constraint as the other
 * hook tests in this repo).
 */

import { createElement } from "react";
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useMonotonicWidth } from "../hooks/useMonotonicWidth";

afterEach(() => cleanup());

type ROCallback = () => void;

function Probe() {
  const { ref, minWidth } = useMonotonicWidth<HTMLDivElement>();
  return createElement("div", {
    ref,
    "data-testid": "box",
    style: minWidth === undefined ? undefined : { minWidth },
  });
}

function mockRectWidth(el: Element, width: number) {
  vi.spyOn(el, "getBoundingClientRect").mockReturnValue({ width } as DOMRect);
}

function mockRect(el: Element, rect: { left: number; right: number; width: number }) {
  vi.spyOn(el, "getBoundingClientRect").mockReturnValue(rect as DOMRect);
}

describe("useMonotonicWidth", () => {
  it("locks the max width seen and ignores later shrinks", () => {
    let roCallback: ROCallback = () => {};
    function FakeResizeObserver(cb: ROCallback) {
      roCallback = cb;
    }
    FakeResizeObserver.prototype.observe = vi.fn();
    FakeResizeObserver.prototype.disconnect = vi.fn();
    FakeResizeObserver.prototype.unobserve = vi.fn();
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
    try {
      const { getByTestId } = render(createElement(Probe));
      const box = getByTestId("box");
      expect(box.getAttribute("style")).toBeNull();

      mockRectWidth(box, 100);
      act(() => roCallback());
      expect(box.style.minWidth).toBe("100px");

      mockRectWidth(box, 300);
      act(() => roCallback());
      expect(box.style.minWidth).toBe("300px");

      mockRectWidth(box, 200);
      act(() => roCallback());
      expect(box.style.minWidth).toBe("300px");
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("clamps the locked minimum when the parent shrinks (zoom change)", () => {
    let roCallback: ROCallback = () => {};
    function FakeResizeObserver(cb: ROCallback) {
      roCallback = cb;
    }
    FakeResizeObserver.prototype.observe = vi.fn();
    FakeResizeObserver.prototype.disconnect = vi.fn();
    FakeResizeObserver.prototype.unobserve = vi.fn();
    vi.stubGlobal("ResizeObserver", FakeResizeObserver);
    try {
      const { getByTestId } = render(createElement(Probe));
      const box = getByTestId("box");
      const parent = box.parentElement!;

      mockRect(box, { left: 42, right: 342, width: 300 });
      mockRect(parent, { left: 0, right: 342, width: 342 });
      act(() => roCallback());
      expect(box.style.minWidth).toBe("300px");

      // Zoom-in: the parent re-lays out narrower; the stale locked minimum
      // must follow or the bubble overflows into a horizontal scrollbar.
      mockRect(box, { left: 42, right: 192, width: 150 });
      mockRect(parent, { left: 0, right: 192, width: 192 });
      act(() => roCallback());
      expect(box.style.minWidth).toBe("150px");

      // Zoom back out: the lock re-expands to the historical max.
      mockRect(box, { left: 42, right: 342, width: 300 });
      mockRect(parent, { left: 0, right: 342, width: 342 });
      act(() => roCallback());
      expect(box.style.minWidth).toBe("300px");
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
