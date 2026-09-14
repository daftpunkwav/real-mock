"use client";

/**
 * @file useMonotonicWidth.ts
 * @description Width that only grows: observes the element and locks the max
 * width seen so far as min-width, so expanding/collapsing content (timelines,
 * streamed text) never shrinks the bubble and causes layout jitter.
 */

import { useEffect, useRef, useState } from "react";

export function useMonotonicWidth<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [minWidth, setMinWidth] = useState<number | undefined>(undefined);

  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      const width = el.getBoundingClientRect().width;
      // Strictly-greater guard: never feed our own min-width back into state.
      setMinWidth((prev) => (prev === undefined || width > prev ? width : prev));
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return { ref, minWidth };
}
