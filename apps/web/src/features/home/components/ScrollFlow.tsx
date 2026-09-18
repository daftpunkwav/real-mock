"use client";

import { useRef, type ReactNode } from "react";
import {
  motion,
  useReducedMotion,
  useScroll,
  useTransform,
  type MotionValue,
} from "framer-motion";

/**
 * Scroll-linked reading flow: a section's blocks drift in from the right as
 * the user scrolls into it — each later item starts further right and catches
 * up, so the row reads as a leftward stream instead of a linear pop.
 * useFlowProgress owns the section ref; FlowItem maps that shared progress to
 * each item's x/opacity. Under prefers-reduced-motion everything is static.
 */
export function useFlowProgress<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const reduce = useReducedMotion();
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start 0.92", "start 0.42"],
  });
  return { ref, progress: scrollYProgress, reduce };
}

export function FlowItem({
  progress,
  reduce,
  index = 0,
  className,
  children,
}: {
  progress: MotionValue<number>;
  reduce: boolean | null;
  index?: number;
  className?: string;
  children: ReactNode;
}) {
  if (reduce) {
    return <div className={className}>{children}</div>;
  }
  return <FlowMotion progress={progress} index={index} className={className}>{children}</FlowMotion>;
}

function FlowMotion({
  progress,
  index,
  className,
  children,
}: {
  progress: MotionValue<number>;
  index: number;
  className?: string;
  children: ReactNode;
}) {
  const x = useTransform(progress, [0, 1], [150 + index * 80, 0]);
  const opacity = useTransform(progress, [0, 0.55], [0, 1]);
  return (
    <motion.div style={{ x, opacity }} className={className}>
      {children}
    </motion.div>
  );
}
