"use client";

import { useEffect } from "react";
import type { RefObject } from "react";
import type { HeadInstance } from "./talkingheadTypes";

/** Periodically pull the line of sight and head posture back to the camera to offset the offset of the model's idle movement. */
export function useTalkingHeadGaze(headRef: RefObject<HeadInstance | null>, speaking: boolean) {
  useEffect(() => {
    const head = headRef.current;
    if (!head) return;
    const lockGaze = () => {
      try {
        head.setBaselineValue?.("eyesLookDown", 0);
        head.setFixedValue?.("eyesLookDown", 0, 180);
        head.setValue("eyesLookDown", 0, 180);
        head.setValue("eyesLookUp", 0.08, 180);
        head.setValue("headRotateX", 0.1, 250);
        head.lookAtCamera?.(speaking ? 700 : 1200);
        head.makeEyeContact?.(speaking ? 900 : 2000);
      } catch {
        /* ignore */
      }
    };
    lockGaze();
    const id = window.setInterval(lockGaze, 2800);
    return () => window.clearInterval(id);
    // headRef is a stable useRef object reference, adding dependencies is only used to satisfy exhaustive-deps
  }, [speaking, headRef]);
}
