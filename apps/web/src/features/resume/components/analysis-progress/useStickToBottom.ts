"use client";

/**
 * @file useStickToBottom
 * @description Auto-scroll a log container while the user stays near the bottom.
 */

import { useEffect, useRef } from "react";

export function useStickToBottom(dep: number) {
  const ref = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  useEffect(() => {
    const el = ref.current;
    if (!el || !stick.current) return;
    el.scrollTop = el.scrollHeight;
  }, [dep]);
  return {
    ref,
    onScroll: () => {
      const el = ref.current;
      if (!el) return;
      stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 64;
    },
  };
}
