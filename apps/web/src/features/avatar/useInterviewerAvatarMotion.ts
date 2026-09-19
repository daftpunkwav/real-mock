"use client";

import { useEffect, useState } from "react";

/** Real-time performance parameters (mouth shape/wink) of the interviewer's 2D portrait. */
export interface InterviewerAvatarMotion {
  mouthOpen: number;
  blink: number;
}

/**
 * 2D portrait mouth shape and blinking:
 * - Lip shape priority follows TTS audio level (threshold 0.03, shaped curve consistent with 3D channel),
 * Low level forces shutting up;
 * - Blinks are independent cycles of randomly spaced intervals of 2.8–6s.
 */
export function useInterviewerAvatarMotion(
  speaking: boolean,
  audioLevel: number,
): InterviewerAvatarMotion {
  const [mouthOpen, setMouthOpen] = useState(0);
  const [blink, setBlink] = useState(1);

  useEffect(() => {
    if (!speaking) {
      setMouthOpen(0);
      return;
    }
    // Low level forces shutting up
    if (audioLevel < 0.03) {
      setMouthOpen(0);
      return;
    }
    const shaped = Math.pow(Math.min(1, (audioLevel - 0.03) / 0.75), 0.85);
    setMouthOpen(Math.min(0.95, 0.12 + shaped * 0.88));
  }, [speaking, audioLevel]);

  // randomly spaced blink loop
  useEffect(() => {
    let closed = false;
    const timers = new Set<ReturnType<typeof setTimeout>>();
    const later = (fn: () => void, ms: number) => {
      const id = setTimeout(() => {
        timers.delete(id);
        if (closed) return;
        fn();
      }, ms);
      timers.add(id);
    };
    const schedule = () => {
      later(() => {
        setBlink(0.08);
        later(() => {
          setBlink(1);
          schedule();
        }, 120);
      }, 2800 + Math.random() * 3200);
    };
    schedule();
    return () => {
      closed = true;
      timers.forEach((id) => clearTimeout(id));
    };
  }, []);

  return { mouthOpen, blink };
}
