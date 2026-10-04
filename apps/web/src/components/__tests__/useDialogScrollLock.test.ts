// @vitest-environment jsdom
/**
 * @file useDialogScrollLock.test.ts
 * @description The scrollbar slot stays reserved only when a scrollbar was
 * actually present; on fit-to-viewport pages a reserved gutter would shrink
 * the layout for the lifetime of the dialog.
 */

import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useDialogScrollLock } from "../useDialogScrollLock";

function stubDimensions(scrollHeight: number, clientHeight: number) {
  const sh = vi
    .spyOn(document.documentElement, "scrollHeight", "get")
    .mockReturnValue(scrollHeight);
  const ch = vi
    .spyOn(document.documentElement, "clientHeight", "get")
    .mockReturnValue(clientHeight);
  return () => {
    sh.mockRestore();
    ch.mockRestore();
  };
}

afterEach(() => {
  document.documentElement.style.overflow = "";
  document.documentElement.style.scrollbarGutter = "";
});

describe("useDialogScrollLock", () => {
  it("freezes scrolling and keeps the scrollbar slot when the page scrolls", () => {
    const restore = stubDimensions(2000, 800);
    const root = document.documentElement;
    const { unmount } = renderHook(() => {
      useDialogScrollLock(true);
    });

    expect(root.style.overflow).toBe("hidden");
    expect(root.style.scrollbarGutter).toBe("stable");

    unmount();
    expect(root.style.overflow).toBe("");
    expect(root.style.scrollbarGutter).toBe("");
    restore();
  });

  it("does not shrink a page that fits the viewport", () => {
    const restore = stubDimensions(0, 0);
    const root = document.documentElement;
    const { unmount } = renderHook(() => useDialogScrollLock(true));

    expect(root.style.overflow).toBe("hidden");
    expect(root.style.scrollbarGutter).toBe("");

    unmount();
    expect(root.style.overflow).toBe("");
    restore();
  });
});
