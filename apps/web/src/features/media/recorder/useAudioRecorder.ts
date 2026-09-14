"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  MIN_SPEECH_CHUNKS,
  MIN_TEXT_CHARS,
  TARGET_SAMPLE_RATE,
} from "./audioRecorderConstants";
import { encodeBase64, safeCloseAudioContext } from "./audioRecorderPcm";
import type { SpeechRecognition } from "./audioRecorderTypes";
import type { RecorderInternalRefs } from "./recorderInternalRefs";
import { useRecorderCaptureArm } from "./useRecorderCaptureArm";
import { useRecorderMicBootstrap } from "./useRecorderMicBootstrap";

/** VAD and PCM capture hook with ASR-assisted silence commits. */
export function useAudioRecorder(
  enabled: boolean,
  onSilence: (pcmBase64: string, partialText: string, sampleRate: number) => void,
  onPartial?: (text: string) => void,
  onSpeechActivity?: () => void,
  onBargeCandidate?: () => void,
  captureEnabled: boolean = true,
) {
  const ctxRef = useRef<AudioContext | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Int16Array[]>([]);
  const chunksBytesRef = useRef(0);
  const speechChunksRef = useRef(0);
  const silenceStartRef = useRef<number | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const sessionRef = useRef(0);
  const finalsRef = useRef("");
  const interimRef = useRef("");
  const lastSpeechActivityRef = useRef(0);
  const bargeLoudSinceRef = useRef<number | null>(null);
  const lastBargeEmitRef = useRef(0);
  const asrLangRef = useRef<"zh-CN" | "en-US">("zh-CN");
  const captureEnabledRef = useRef(captureEnabled);
  const captureArmAtRef = useRef(0);
  const asrAllowedRef = useRef(false);
  const startAsrRef = useRef<() => void>(() => {});
  const onSilenceRef = useRef(onSilence);
  const onPartialRef = useRef(onPartial);
  const onSpeechActivityRef = useRef(onSpeechActivity);
  const onBargeCandidateRef = useRef(onBargeCandidate);
  const ringChunksRef = useRef<Int16Array[]>([]);
  const ringBytesRef = useRef(0);
  const pendingSeedRef = useRef<Int16Array[] | null>(null);
  const lastInterimUpdateRef = useRef(0);
  const lastFinalAtRef = useRef(0);
  const emitSilenceRef = useRef(() => {});
  const [isRecording, setIsRecording] = useState(false);
  const [partialText, setPartialText] = useState("");
  const [micError, setMicError] = useState("");

  const refs: RecorderInternalRefs = {
    ctxRef,
    processorRef,
    sourceRef,
    streamRef,
    chunksRef,
    chunksBytesRef,
    speechChunksRef,
    silenceStartRef,
    recognitionRef,
    sessionRef,
    finalsRef,
    interimRef,
    lastSpeechActivityRef,
    bargeLoudSinceRef,
    lastBargeEmitRef,
    asrLangRef,
    captureEnabledRef,
    captureArmAtRef,
    asrAllowedRef,
    startAsrRef,
    onSilenceRef,
    onPartialRef,
    onSpeechActivityRef,
    onBargeCandidateRef,
    ringChunksRef,
    ringBytesRef,
    pendingSeedRef,
    lastInterimUpdateRef,
    lastFinalAtRef,
    emitSilenceRef,
  };

  useEffect(() => {
    onSilenceRef.current = onSilence;
    onPartialRef.current = onPartial;
    onSpeechActivityRef.current = onSpeechActivity;
    onBargeCandidateRef.current = onBargeCandidate;
  }, [onSilence, onPartial, onSpeechActivity, onBargeCandidate]);

  const isCapturing = () =>
    captureEnabledRef.current && Date.now() >= captureArmAtRef.current;

  const stopAsr = useCallback(() => {
    asrAllowedRef.current = false;
    try {
      const rec = recognitionRef.current;
      if (rec) {
        rec.onend = null;
        rec.stop();
      }
    } catch {
      /* ignore */
    }
    recognitionRef.current = null;
  }, []);

  const resetCaptureState = useCallback(() => {
    chunksRef.current = [];
    chunksBytesRef.current = 0;
    speechChunksRef.current = 0;
    silenceStartRef.current = null;
    finalsRef.current = "";
    interimRef.current = "";
    lastInterimUpdateRef.current = 0;
    lastFinalAtRef.current = 0;
  }, []);

  const clearCaptureBuffers = useCallback(() => {
    resetCaptureState();
    bargeLoudSinceRef.current = null;
    setPartialText("");
  }, [resetCaptureState]);

  const seedCaptureFromRing = useCallback(() => {
    const seed = ringChunksRef.current.map((c) => c.slice());
    pendingSeedRef.current = seed.length ? seed : null;
  }, []);

  emitSilenceRef.current = () => {
    if (!isCapturing()) {
      clearCaptureBuffers();
      return;
    }
    const text = `${finalsRef.current}${interimRef.current}`.trim();
    const hasSpeech =
      speechChunksRef.current >= MIN_SPEECH_CHUNKS ||
      text.length >= MIN_TEXT_CHARS;
    const nativeRate = ctxRef.current?.sampleRate || TARGET_SAMPLE_RATE;
    const b64 = hasSpeech ? encodeBase64(chunksRef.current, nativeRate) : "";
    resetCaptureState();
    setPartialText("");
    if (b64 || text) {
      onSilenceRef.current(b64, text, TARGET_SAMPLE_RATE);
    }
  };

  const stop = useCallback(() => {
    sessionRef.current += 1;
    setIsRecording(false);
    processorRef.current?.disconnect();
    processorRef.current = null;
    sourceRef.current?.disconnect();
    sourceRef.current = null;
    safeCloseAudioContext(ctxRef.current);
    ctxRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    stopAsr();
    resetCaptureState();
    bargeLoudSinceRef.current = null;
    ringChunksRef.current = [];
    ringBytesRef.current = 0;
    pendingSeedRef.current = null;
    asrLangRef.current = "zh-CN";
  }, [stopAsr, resetCaptureState]);

  const flush = useCallback(() => {
    if (!streamRef.current) return;
    emitSilenceRef.current();
  }, []);

  useRecorderCaptureArm(
    captureEnabled,
    refs,
    clearCaptureBuffers,
    stopAsr,
    setPartialText,
  );
  useRecorderMicBootstrap(
    enabled,
    refs,
    stop,
    setIsRecording,
    setMicError,
    setPartialText,
  );

  return {
    stop,
    flush,
    clearCaptureBuffers,
    seedCaptureFromRing,
    isRecording,
    partialText,
    micError,
  };
}
