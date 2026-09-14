"use client";

import { useEffect, useRef } from "react";
import type { RefObject } from "react";
import type { HeadInstance } from "./talkingheadTypes";

/** Volume → Lip shape: low-level closed mouth, smooth curve with attack/attenuation (threshold and curve parameters must be consistent with useInterviewerAvatarMotion) */
function mapAudioToMouth(level: number, speaking: boolean): number {
  if (!speaking) return 0;
  if (level < 0.03) return 0;
  const shaped = Math.pow(Math.min(1, (level - 0.03) / 0.75), 0.85);
  return Math.min(0.95, 0.12 + shaped * 0.88);
}

/** Volume → Smooth mouth shape (fast attack, slow decay), rAF cycle drive mouth/jaw and smile linkage. */
export function useTalkingHeadMouth(
  headRef: RefObject<HeadInstance | null>,
  audioLevel: number,
  speaking: boolean,
) {
  const mouthSmoothRef = useRef(0);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    const head = headRef.current;
    if (!head) return;

    const target = mapAudioToMouth(audioLevel, speaking);
    const tick = () => {
      const cur = mouthSmoothRef.current;
      const attack = 0.45;
      const release = 0.18;
      const k = target > cur ? attack : release;
      const next = cur + (target - cur) * k;
      mouthSmoothRef.current = Math.abs(next - target) < 0.008 ? target : next;
      try {
        const open = mouthSmoothRef.current;
        head.setValue("mouthOpen", open, 30);
        head.setValue("jawOpen", open * 0.55, 30);
        if (speaking && open > 0.2) {
          head.setValue("mouthSmile", Math.min(0.25, open * 0.2), 40);
        }
      } catch {
        /* morph may not be ready yet */
      }
      if (speaking || mouthSmoothRef.current > 0.01) {
        rafRef.current = requestAnimationFrame(tick);
      }
    };
    cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
    // headRef is a stable useRef object reference, adding dependencies is only used to satisfy exhaustive-deps
  }, [audioLevel, speaking, headRef]);
}
