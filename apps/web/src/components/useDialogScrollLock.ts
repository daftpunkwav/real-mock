"use client";

import { useEffect } from "react";

/**
 * Freeze background scrolling while a dialog is open.
 *
 * Pages scroll at the document level (AppShell's <main> grows with its content),
 * so the root element is the scroll owner to freeze; this also covers any page
 * whose inner container would otherwise keep scrolling.
 */
export function useDialogScrollLock(active: boolean) {
  useEffect(() => {
    if (!active) return;
    const root = document.documentElement;
    const previousOverflow = root.style.overflow;
    const previousGutter = root.style.scrollbarGutter;
    root.style.overflow = "hidden";
    // Keep the scrollbar slot reserved, otherwise content widens by the
    // scrollbar width the moment the viewport scrollbar disappears.
    root.style.scrollbarGutter = "stable";
    return () => {
      root.style.overflow = previousOverflow;
      root.style.scrollbarGutter = previousGutter;
    };
  }, [active]);
}
