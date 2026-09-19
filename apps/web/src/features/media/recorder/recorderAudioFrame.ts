/** ScriptProcessor audio frame: VAD, barge-in detection, PCM capture, and silence commits. */

import {
  BARGE_RMS_THRESHOLD,
  BARGE_SUSTAIN_MS,
  RING_BUFFER_MAX_BYTES,
  SILENCE_RMS_THRESHOLD,
  SPEECH_ACTIVITY_THROTTLE_MS,
} from "./audioRecorderConstants";
import {
  appendChunkWithCap,
  floatTo16BitPCM,
  shouldCommitOnSilence,
  trimRing,
} from "./audioRecorderPcm";

export interface RecorderFrameRefs {
  captureEnabled: () => boolean;
  captureArmAt: () => number;
  /** Live chunks getter; reset replaces the array reference. */
  chunks: () => Int16Array[];
  chunksBytes: { current: number };
  speechChunks: { current: number };
  silenceStart: { current: number | null };
  ringChunks: () => Int16Array[];
  ringBytes: { current: number };
  bargeLoudSince: { current: number | null };
  lastBargeEmit: { current: number };
  lastSpeechActivity: { current: number };
  finals: { current: string };
  interim: { current: string };
  lastInterimUpdate: { current: number };
  lastFinalAt: { current: number };
  onBargeCandidate?: () => void;
  onSpeechActivity?: () => void;
  emitSilence: () => void;
}

export function processRecorderAudioFrame(
  input: Float32Array,
  frameSession: number,
  activeSession: number,
  refs: RecorderFrameRefs,
): boolean {
  if (frameSession !== activeSession) return false;

  let sum = 0;
  for (let i = 0; i < input.length; i++) sum += (input[i] ?? 0) * (input[i] ?? 0);
  const rms = Math.sqrt(sum / input.length);
  const now = Date.now();
  const pcm = floatTo16BitPCM(input);

  if (!refs.captureEnabled()) {
    refs.ringChunks().push(pcm);
    refs.ringBytes.current += pcm.byteLength;
    trimRing(refs.ringChunks(), refs.ringBytes, RING_BUFFER_MAX_BYTES);

    if (rms >= BARGE_RMS_THRESHOLD) {
      if (refs.bargeLoudSince.current == null) {
        refs.bargeLoudSince.current = now;
      } else if (
        now - refs.bargeLoudSince.current >= BARGE_SUSTAIN_MS &&
        now - refs.lastBargeEmit.current >= 1200
      ) {
        refs.lastBargeEmit.current = now;
        refs.bargeLoudSince.current = now;
        refs.onBargeCandidate?.();
      }
    } else {
      refs.bargeLoudSince.current = null;
    }
    return true;
  }

  if (now < refs.captureArmAt()) {
    return true;
  }

  appendChunkWithCap(refs.chunks(), refs.chunksBytes, pcm);

  if (rms >= SILENCE_RMS_THRESHOLD) {
    refs.speechChunks.current += 1;
    refs.silenceStart.current = null;
    if (now - refs.lastSpeechActivity.current >= SPEECH_ACTIVITY_THROTTLE_MS) {
      refs.lastSpeechActivity.current = now;
      refs.onSpeechActivity?.();
    }
  } else {
    refs.bargeLoudSince.current = null;
    if (!refs.silenceStart.current) refs.silenceStart.current = now;
    else if (
      shouldCommitOnSilence({
        silenceStartMs: refs.silenceStart.current,
        chunkCount: refs.chunks().length,
        speechChunks: refs.speechChunks.current,
        finals: refs.finals.current,
        interim: refs.interim.current,
        lastInterimUpdate: refs.lastInterimUpdate.current,
        lastFinalAt: refs.lastFinalAt.current,
      })
    ) {
      refs.emitSilence();
    }
  }
  return true;
}
