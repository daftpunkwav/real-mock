"use client";

/**
 * @file useInViewReveal.ts
 * @description One-shot in-view flag for score ring / radar enter animation.
 */

import { useEffect, useRef, useState } from "react";
import { useInView, useReducedMotion, type UseInViewOptions } from "framer-motion";

/**
 * One-shot reveal flag: true after the element first enters view.
 * Uses once:true with the given margin (default -30px); honors reduced motion.
 */
export function useInViewReveal(margin: UseInViewOptions["margin"] = "-30px") {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin });
  const reduce = useReducedMotion();
  const [shown, setShown] = useState(false);

  useEffect(() => {
    if (!inView) return;
    if (reduce) {
      setShown(true);
      return;
    }
    const raf = requestAnimationFrame(() => setShown(true));
    return () => cancelAnimationFrame(raf);
  }, [inView, reduce]);

  return { ref, shown, reduce };
}
