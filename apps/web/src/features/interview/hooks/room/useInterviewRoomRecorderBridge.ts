"use client";

import { useEffect } from "react";
import { useAudioRecorder } from "@/features/media";
import type { RecorderBridge } from "./useInterviewRoomActions";
import type { AnyRef } from "./useInterviewRoomEvents";

interface InterviewRoomRecorderBridgeDeps {
  micEnabled: boolean;
  captureEnabled: boolean;
  onSilenceStable: (pcm: string, partial: string, sampleRate: number) => void;
  onPartialStable: (text: string) => void;
  onSpeechActivity: () => void;
  onBargeCandidate: () => void;
  recorderRef: AnyRef<RecorderBridge>;
  clearCaptureBuffersRef: AnyRef<() => void>;
  seedCaptureFromRingRef: AnyRef<() => void>;
}

/** Expose recorder state to actions and wire buffer controls into shared refs. */
export function useInterviewRoomRecorderBridge(deps: InterviewRoomRecorderBridgeDeps) {
  const recorder = useAudioRecorder(
    deps.micEnabled,
    deps.onSilenceStable,
    deps.onPartialStable,
    deps.onSpeechActivity,
    deps.onBargeCandidate,
    deps.captureEnabled,
  );

  deps.recorderRef.current = {
    flush: recorder.flush,
    isRecording: recorder.isRecording,
    partialText: recorder.partialText,
    micError: recorder.micError,
  };

  useEffect(() => {
    deps.clearCaptureBuffersRef.current = recorder.clearCaptureBuffers;
    deps.seedCaptureFromRingRef.current = recorder.seedCaptureFromRing;
  }, [recorder.clearCaptureBuffers, recorder.seedCaptureFromRing, deps.clearCaptureBuffersRef, deps.seedCaptureFromRingRef]);

  return {
    isRecording: recorder.isRecording,
    partialText: recorder.partialText,
    micError: recorder.micError,
  };
}
