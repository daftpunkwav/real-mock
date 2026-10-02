"use client";

/**
 * @file useMonotonicWidth.ts
 * @description Width that only grows, clamped to the space actually available:
 * observes the element and locks the max width seen so far as min-width, so
 * expanding/collapsing content (timelines, streamed text) never shrinks the
 * bubble and causes layout jitter. The clamp matters on zoom changes: the page
 * re-lays out in different CSS px, and a stale locked minimum wider than its
 * container would force a horizontal scrollbar until reload.
 */

import { useEffect, useRef, useState } from "react";

export function useMonotonicWidth<T extends HTMLElement>() {
  const ref = useRef<T | null>(null);
  const [minWidth, setMinWidth] = useState<number | undefined>(undefined);

  useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    let maxSeen = 0;
    const measure = () => {
      const width = el.getBoundingClientRect().width;
      if (width > maxSeen) maxSeen = width;
      let next = maxSeen;
      const parent = el.parentElement;
      if (parent) {
        // Space from the element's left edge to the parent's inner right edge:
        // accounts for leading siblings (the avatar) without hard-coded gaps.
        const available = parent.getBoundingClientRect().right - el.getBoundingClientRect().left;
        if (Number.isFinite(available)) next = Math.min(maxSeen, available);
      }
      if (next > 0) {
        setMinWidth((prev) => (prev !== undefined && Math.abs(prev - next) < 0.5 ? prev : next));
      }
    };
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    if (el.parentElement) observer.observe(el.parentElement);
    return () => observer.disconnect();
  }, []);

  return { ref, minWidth };
}
