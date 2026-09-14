/** useAudioRecorder ref ( hook ). */

import type { MutableRefObject, RefObject } from "react";
import type { SpeechRecognition } from "./audioRecorderTypes";

export type RecorderInternalRefs = {
  ctxRef: RefObject<AudioContext | null>;
  processorRef: RefObject<ScriptProcessorNode | null>;
  sourceRef: RefObject<MediaStreamAudioSourceNode | null>;
  streamRef: RefObject<MediaStream | null>;
  chunksRef: RefObject<Int16Array[]>;
  chunksBytesRef: MutableRefObject<number>;
  speechChunksRef: MutableRefObject<number>;
  silenceStartRef: MutableRefObject<number | null>;
  recognitionRef: MutableRefObject<SpeechRecognition | null>;
  sessionRef: MutableRefObject<number>;
  finalsRef: MutableRefObject<string>;
  interimRef: MutableRefObject<string>;
  lastSpeechActivityRef: MutableRefObject<number>;
  bargeLoudSinceRef: MutableRefObject<number | null>;
  lastBargeEmitRef: MutableRefObject<number>;
  asrLangRef: MutableRefObject<"zh-CN" | "en-US">;
  captureEnabledRef: MutableRefObject<boolean>;
  captureArmAtRef: MutableRefObject<number>;
  asrAllowedRef: MutableRefObject<boolean>;
  startAsrRef: MutableRefObject<() => void>;
  ringChunksRef: RefObject<Int16Array[]>;
  ringBytesRef: MutableRefObject<number>;
  pendingSeedRef: MutableRefObject<Int16Array[] | null>;
  lastInterimUpdateRef: MutableRefObject<number>;
  lastFinalAtRef: MutableRefObject<number>;
  onSilenceRef: MutableRefObject<
    (pcmBase64: string, partialText: string, sampleRate: number) => void
  >;
  onPartialRef: MutableRefObject<((text: string) => void) | undefined>;
  onSpeechActivityRef: MutableRefObject<(() => void) | undefined>;
  onBargeCandidateRef: MutableRefObject<(() => void) | undefined>;
  emitSilenceRef: MutableRefObject<() => void>;
};
