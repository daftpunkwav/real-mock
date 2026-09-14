"use client";

import { useEffect } from "react";
import type { RefObject } from "react";
import type { AvatarExpression } from "../contract";
import { EXPRESSION_MORPH, EXPRESSION_TO_MOOD } from "./talkingheadMood";
import type { HeadInstance } from "./talkingheadTypes";

/** Expression → Kunei mood + auxiliary morph (eyebrows/eyes/mouth corners); unknown value falls back to neutral. */
export function useTalkingHeadEmotion(
  headRef: RefObject<HeadInstance | null>,
  emotion: AvatarExpression,
) {
  useEffect(() => {
    const head = headRef.current;
    if (!head) return;
    const mood = EXPRESSION_TO_MOOD[emotion] ?? "neutral";
    try {
      const names = head.getMoodNames?.() || [];
      if (names.length === 0 || names.includes(mood)) {
        head.setMood(mood);
      } else {
        head.setMood("neutral");
      }
    } catch {
      try {
        head.setMood("neutral");
      } catch {
        /* ignore */
      }
    }

    const morph = EXPRESSION_MORPH[emotion] ?? {};
    const trySet = (name: string, val: number) => {
      try {
        head.setValue(name, val, 180);
      } catch {
        /* morph may not exist */
      }
    };
    trySet("browInnerUp", morph.browInnerUp ?? 0);
    trySet("eyeSquintLeft", morph.eyeSquint ?? 0);
    trySet("eyeSquintRight", morph.eyeSquint ?? 0);
    trySet("mouthSmile", morph.mouthSmile ?? 0);
    trySet("eyesClosed", morph.eyesClosed ?? 0);
    // headRef is a stable useRef object reference, adding dependencies is only used to satisfy exhaustive-deps
  }, [emotion, headRef]);
}
