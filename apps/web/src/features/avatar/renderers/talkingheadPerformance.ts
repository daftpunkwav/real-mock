"use client";

import { useEffect, useRef } from "react";
import type { RefObject } from "react";
import { currentTTSLevel } from "../levelSink";
import {
  advanceSyllablePhase,
  followSignal,
  mouthOpenFromLevel,
  syllableShape,
} from "../mouthShape";
import type { HeadInstance } from "./talkingheadTypes";

/**
 * The 3D interviewer's full performance loop: lip sync, syllable-shaped mouth
 * colouring, speech-timed gestures, and a self-managed blink cycle — one rAF
 * per frame driving everything, so the morphs stay in phase with each other.
 *
 * The loop reads the live TTS level from the module-level sink (never React
 * state): the meter updates at frame rate, and pumping it through props used
 * to re-render the whole room per frame.
 */

/** Blink scheduling state (seconds on the performance.now clock). */
interface BlinkState {
  nextAt: number;
  closingUntil: number;
}

function scheduleBlink(now: number, speaking: boolean): BlinkState {
  // Thinking pauses blink a little more; speech stretches the interval.
  const base = speaking ? 3400 : 2600;
  return { nextAt: now + base + Math.random() * 3200, closingUntil: 0 };
}

export function useTalkingHeadPerformance(
  headRef: RefObject<HeadInstance | null>,
  fallbackLevel: number,
  speaking: boolean,
) {
  const smoothRef = useRef(0);
  const rafRef = useRef<number>(0);
  const lastMsRef = useRef(0);
  const phaseRef = useRef(0);
  // nextAt=0 means "not scheduled yet" — performance.now() is page uptime, so
  // the first blink must be scheduled from the first frame's clock, not zero.
  const blinkRef = useRef<BlinkState>({ nextAt: 0, closingUntil: 0 });
  const driftRef = useRef({ target: 0, nextAt: 0 });
  const speakingRef = useRef(speaking);
  speakingRef.current = speaking;

  useEffect(() => {
    const head = headRef.current;
    if (!head) return;

    const tick = (nowMs: number) => {
      const dt = lastMsRef.current ? Math.min(100, nowMs - lastMsRef.current) : 16.7;
      lastMsRef.current = nowMs;
      const now = nowMs / 1000;
      const isSpeaking = speakingRef.current;

      // Live meter from the sink wins; the prop is a fallback (tests, debug page).
      const level = isSpeaking ? Math.max(currentTTSLevel(), fallbackLevel) : 0;
      const target = mouthOpenFromLevel(level, isSpeaking);
      const open = followSignal(smoothRef.current, target, dt);
      smoothRef.current = open;
      // Energy = how much voice is actually flowing right now.
      const energy = Math.max(0, Math.min(1, (open - 0.12) / 0.83));
      phaseRef.current = advanceSyllablePhase(phaseRef.current, energy, dt);
      const shape = syllableShape(phaseRef.current, energy);

      try {
        // Lip sync: open + jaw, with per-syllable wide/round colouring.
        head.setValue("mouthOpen", open, 30);
        head.setValue("jawOpen", open * (0.55 - shape.round * 0.25), 30);
        if (shape.wide > 0.02) head.setValue("mouthSmileLeft", shape.wide * 0.5, 40);
        if (shape.round > 0.02) head.setValue("mouthPucker", shape.round * 0.6, 40);
        if (isSpeaking && open > 0.2) {
          head.setValue("mouthSmile", Math.min(0.25, open * 0.2), 40);
        }

        // Speech gestures: small nods riding the syllable beat and a slow
        // sideways drift (rotateY/Z are gaze-safe; gaze owns rotateX).
        if (isSpeaking && energy > 0.05) {
          const nod = Math.sin(phaseRef.current) * 0.35 * energy;
          head.setValue("headRotateZ", nod * 0.04, 90);
          if (now >= driftRef.current.nextAt) {
            driftRef.current = {
              target: (Math.random() - 0.5) * 0.5,
              nextAt: now + 2.5 + Math.random() * 3.5,
            };
          }
          head.setValue("headRotateY", driftRef.current.target * energy * 0.06, 400);
        } else {
          head.setValue("headRotateZ", 0, 300);
          head.setValue("headRotateY", 0, 300);
        }

        // Self-managed blinking: the library's idle blink is unconfigurable;
        // a deterministic cycle lets speech stretch the interval.
        const blink = blinkRef.current;
        if (blink.nextAt === 0) {
          blinkRef.current = scheduleBlink(now, isSpeaking);
        } else if (blink.closingUntil === 0 && now >= blink.nextAt) {
          blink.closingUntil = now + 0.12;
          head.setValue("eyeBlinkLeft", 1, 60);
          head.setValue("eyeBlinkRight", 1, 60);
        } else if (blink.closingUntil !== 0 && now >= blink.closingUntil) {
          head.setValue("eyeBlinkLeft", 0, 90);
          head.setValue("eyeBlinkRight", 0, 90);
          blinkRef.current = scheduleBlink(now, isSpeaking);
        }
      } catch {
        /* morphs may not exist on every model — stay silent */
      }

      if (isSpeaking || smoothRef.current > 0.01 || blinkRef.current.closingUntil !== 0) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        // Fully idle: park the loop until the next speaking flip re-runs the
        // effect (saves a per-frame wakeup while the interviewer listens).
        lastMsRef.current = 0;
      }
    };
    cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafRef.current);
    // headRef is a stable useRef object reference, adding dependencies is only used to satisfy exhaustive-deps
  }, [speaking, headRef, fallbackLevel]);
}
