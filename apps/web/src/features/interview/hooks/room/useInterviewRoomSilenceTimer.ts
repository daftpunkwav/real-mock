"use client";

import { useEffect, useRef } from "react";
import type { ClientEvent } from "@/types";
import type { AnyRef } from "./useInterviewRoomEvents";

interface InterviewRoomSilenceTimerOpts {
  micEnabled: boolean;
  silenceNudgeMs: number;
  waitMsRef: AnyRef<number>;
  sendRef: AnyRef<(p: ClientEvent) => boolean>;
  /** Shared room ref used by both event and STT callbacks to reset the timer. */
  bumpSilenceTimerRef: AnyRef<() => void>;
}

/**
 * Fallback wake for the server-owned think window. The SERVER fires the nudge
 * on expiry (immune to client-side STT failures); this client timer only
 * wakes it early, so it must never gate on transient states like STT errors.
 */
export function useInterviewRoomSilenceTimer(opts: InterviewRoomSilenceTimerOpts) {
  const { micEnabled, silenceNudgeMs, waitMsRef, sendRef, bumpSilenceTimerRef } = opts;
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const clear = () => {
      if (silenceTimerRef.current) {
        clearTimeout(silenceTimerRef.current);
        silenceTimerRef.current = null;
      }
    };
    bumpSilenceTimerRef.current = () => {
      if (!micEnabled) return;
      clear();
      silenceTimerRef.current = setTimeout(() => {
        sendRef.current({ type: "silence_timeout" });
      }, waitMsRef.current || silenceNudgeMs);
    };
    if (!micEnabled) {
      clear();
      return;
    }
    const graceMs = Math.min(12_000, Math.max(4_000, Math.floor(silenceNudgeMs * 0.45)));
    silenceTimerRef.current = setTimeout(() => {
      bumpSilenceTimerRef.current();
    }, graceMs);
    return clear;
  }, [micEnabled, silenceNudgeMs, waitMsRef, sendRef, bumpSilenceTimerRef]);
}
