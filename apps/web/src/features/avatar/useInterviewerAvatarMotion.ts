"use client";

import { useEffect, useState } from "react";
import { currentTTSLevel } from "./levelSink";
import {
  advanceSyllablePhase,
  followSignal,
  mouthOpenFromLevel,
  syllableShape,
} from "./mouthShape";

/** Real-time performance parameters (mouth/wink/speech-bob) of the interviewer's 2D portrait. */
export interface InterviewerAvatarMotion {
  mouthOpen: number;
  /** Syllable colouring from the shared mouth-shape module (3D/2D same math). */
  mouthWide: number;
  mouthRound: number;
  blink: number;
  /** Speech-timed head bob in SVG units (0 when silent). */
  bob: number;
}

const IDLE: InterviewerAvatarMotion = {
  mouthOpen: 0,
  mouthWide: 0,
  mouthRound: 0,
  blink: 1,
  bob: 0,
};

/**
 * 2D portrait performance: lips follow the shared TTS level sink with the same
 * curve and syllable colouring as the 3D channel, blinks run on random
 * 2.8–6s intervals, and the head bobs slightly with the speech beat.
 *
 * State updates are confined to the portrait subtree (this hook has no
 * room-level consumers), so the per-frame setState is acceptable here.
 */
export function useInterviewerAvatarMotion(
  speaking: boolean,
  fallbackLevel: number,
): InterviewerAvatarMotion {
  const [motion, setMotion] = useState<InterviewerAvatarMotion>(IDLE);

  useEffect(() => {
    if (!speaking) {
      setMotion(IDLE);
      return;
    }
    let raf = 0;
    let lastMs = 0;
    let smooth = 0;
    let phase = 0;
    const tick = (nowMs: number) => {
      const dt = lastMs ? Math.min(100, nowMs - lastMs) : 16.7;
      lastMs = nowMs;
      const level = Math.max(currentTTSLevel(), fallbackLevel);
      const open = followSignal(smooth, mouthOpenFromLevel(level, true), dt);
      smooth = open;
      const energy = Math.max(0, Math.min(1, (open - 0.12) / 0.83));
      phase = advanceSyllablePhase(phase, energy, dt);
      const shape = syllableShape(phase, energy);
      // Functional update: the blink loop writes into the same state object,
      // so a whole-object set here would erase an in-progress blink within
      // one frame (eyes would stay open for the whole utterance).
      setMotion((m) => ({
        ...m,
        mouthOpen: open,
        mouthWide: shape.wide,
        mouthRound: shape.round,
        bob: Math.sin(phase) * 1.6 * energy,
      }));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [speaking, fallbackLevel]);

  // Blink loop (independent of the speaking loop; timers fully cleaned up).
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
      later(
        () => {
          setMotion((m) => ({ ...m, blink: 0.08 }));
          later(() => {
            setMotion((m) => ({ ...m, blink: 1 }));
            schedule();
          }, 120);
        },
        2800 + Math.random() * 3200,
      );
    };
    schedule();
    return () => {
      closed = true;
      timers.forEach((id) => clearTimeout(id));
    };
  }, []);

  return motion;
}
