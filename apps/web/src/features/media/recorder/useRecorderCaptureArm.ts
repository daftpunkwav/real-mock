import { useEffect } from "react";
import {
  CAPTURE_ARM_AFTER_BARGE_MS,
  CAPTURE_ARM_DELAY_MS,
  MIN_SPEECH_CHUNKS,
} from "./audioRecorderConstants";
import type { RecorderInternalRefs } from "./recorderInternalRefs";

/** Arm capture with ring seed and delayed ASR start. */
export function useRecorderCaptureArm(
  captureEnabled: boolean,
  refs: RecorderInternalRefs,
  clearCaptureBuffers: () => void,
  stopAsr: () => void,
  setPartialText: (v: string) => void,
) {
  const {
    captureEnabledRef,
    captureArmAtRef,
    pendingSeedRef,
    chunksRef,
    chunksBytesRef,
    speechChunksRef,
    silenceStartRef,
    bargeLoudSinceRef,
    finalsRef,
    interimRef,
    ringChunksRef,
    ringBytesRef,
    startAsrRef,
    streamRef,
  } = refs;

  useEffect(() => {
    captureEnabledRef.current = captureEnabled;
    if (!captureEnabled) {
      clearCaptureBuffers();
      ringChunksRef.current = [];
      ringBytesRef.current = 0;
      stopAsr();
      return;
    }
    const seed = pendingSeedRef.current;
    pendingSeedRef.current = null;
    const armMs = seed?.length ? CAPTURE_ARM_AFTER_BARGE_MS : CAPTURE_ARM_DELAY_MS;
    if (seed?.length) {
      chunksRef.current = seed;
      let bytes = 0;
      for (const c of seed) bytes += c.byteLength;
      chunksBytesRef.current = bytes;
      speechChunksRef.current = Math.max(
        MIN_SPEECH_CHUNKS,
        Math.min(seed.length, 8),
      );
      silenceStartRef.current = null;
      bargeLoudSinceRef.current = null;
      finalsRef.current = "";
      interimRef.current = "";
      ringChunksRef.current = [];
      ringBytesRef.current = 0;
      setPartialText("");
    } else {
      clearCaptureBuffers();
      ringChunksRef.current = [];
      ringBytesRef.current = 0;
    }
    captureArmAtRef.current = Date.now() + armMs;
    const t = window.setTimeout(() => {
      if (!captureEnabledRef.current || !streamRef.current) return;
      startAsrRef.current();
    }, armMs);
    return () => clearTimeout(t);
  }, [
    captureEnabled,
    clearCaptureBuffers,
    stopAsr,
    captureEnabledRef,
    captureArmAtRef,
    pendingSeedRef,
    chunksRef,
    chunksBytesRef,
    speechChunksRef,
    silenceStartRef,
    bargeLoudSinceRef,
    finalsRef,
    interimRef,
    ringChunksRef,
    ringBytesRef,
    startAsrRef,
    streamRef,
  ]);
}
