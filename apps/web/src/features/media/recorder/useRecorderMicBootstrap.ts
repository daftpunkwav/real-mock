import { useEffect } from "react";
import { getTranslator } from "@/i18n/resolve";
import { TARGET_SAMPLE_RATE } from "./audioRecorderConstants";
import { createSpeechRecognitionSession } from "./audioRecorderAsr";
import {
  attachRecorderProcessor,
  createRecorderAudioContext,
  openMicStream,
} from "./recorderMediaGraph";
import { safeCloseAudioContext } from "./audioRecorderPcm";
import type { RecorderFrameRefs } from "./recorderAudioFrame";
import type { RecorderInternalRefs } from "./recorderInternalRefs";

/** Open the mic graph and ASR session while enabled. */
export function useRecorderMicBootstrap(
  enabled: boolean,
  refs: RecorderInternalRefs,
  stop: () => void,
  setIsRecording: (v: boolean) => void,
  setMicError: (v: string) => void,
  setPartialText: (v: string) => void,
) {
  const {
    captureEnabledRef,
    captureArmAtRef,
    asrAllowedRef,
    ctxRef,
    processorRef,
    sourceRef,
    streamRef,
    sessionRef,
    recognitionRef,
    asrLangRef,
    startAsrRef,
    chunksRef,
    chunksBytesRef,
    speechChunksRef,
    silenceStartRef,
    ringChunksRef,
    ringBytesRef,
    bargeLoudSinceRef,
    lastBargeEmitRef,
    lastSpeechActivityRef,
    finalsRef,
    interimRef,
    lastInterimUpdateRef,
    lastFinalAtRef,
    onBargeCandidateRef,
    onSpeechActivityRef,
    onPartialRef,
    emitSilenceRef,
  } = refs;

  const isCapturing = () =>
    captureEnabledRef.current && Date.now() >= captureArmAtRef.current;

  useEffect(() => {
    if (!enabled) {
      stop();
      setPartialText("");
      return;
    }

    stop();
    const session = sessionRef.current;
    setMicError("");
    setPartialText("");

    (async () => {
      try {
        const stream = await openMicStream();
        if (session !== sessionRef.current) {
          stream.getTracks().forEach((t) => t.stop());
          return;
        }

        streamRef.current = stream;
        const { ctx, source } = await createRecorderAudioContext(stream);
        if (session !== sessionRef.current) {
          stream.getTracks().forEach((t) => t.stop());
          safeCloseAudioContext(ctx);
          return;
        }
        ctxRef.current = ctx;
        sourceRef.current = source;

        const frameRefs: RecorderFrameRefs = {
          captureEnabled: () => captureEnabledRef.current,
          captureArmAt: () => captureArmAtRef.current,
          // Read the live chunks ref; reset replaces the array.
          chunks: () => chunksRef.current,
          chunksBytes: chunksBytesRef,
          speechChunks: speechChunksRef,
          silenceStart: silenceStartRef,
          ringChunks: () => ringChunksRef.current,
          ringBytes: ringBytesRef,
          bargeLoudSince: bargeLoudSinceRef,
          lastBargeEmit: lastBargeEmitRef,
          lastSpeechActivity: lastSpeechActivityRef,
          finals: finalsRef,
          interim: interimRef,
          lastInterimUpdate: lastInterimUpdateRef,
          lastFinalAt: lastFinalAtRef,
          onBargeCandidate: () => onBargeCandidateRef.current?.(),
          onSpeechActivity: () => onSpeechActivityRef.current?.(),
          emitSilence: () => emitSilenceRef.current(),
        };

        const processor = attachRecorderProcessor(
          ctx,
          source,
          session,
          () => sessionRef.current,
          frameRefs,
        );
        processorRef.current = processor;

        const asr = createSpeechRecognitionSession({
          getSession: () => sessionRef.current,
          isCapturing,
          captureEnabledNow: () => captureEnabledRef.current,
          asrAllowedRef,
          recognitionRef,
          asrLangRef,
          finalsRef,
          interimRef,
          lastFinalAtRef,
          lastInterimUpdateRef,
          setPartialText,
          onPartialRef,
        });
        startAsrRef.current = asr.enableAndStart;
        if (captureEnabledRef.current && isCapturing()) {
          asr.enableAndStart();
        } else if (captureEnabledRef.current) {
          asr.startAfterArm(captureArmAtRef.current - Date.now());
        }

        if (session === sessionRef.current) {
          setIsRecording(true);
        }
      } catch (e) {
        // translator( )
        const msg =
          e instanceof Error ? e.message : getTranslator("media")("recorder.micUnavailable");
        setMicError(msg);
        console.warn("Microphone unavailable", e);
        if (streamRef.current) {
          streamRef.current.getTracks().forEach((t) => t.stop());
          streamRef.current = null;
        }
        safeCloseAudioContext(ctxRef.current);
        ctxRef.current = null;
      }
    })();

    return () => stop();
  }, [enabled, stop, setIsRecording, setMicError, setPartialText]);
}
