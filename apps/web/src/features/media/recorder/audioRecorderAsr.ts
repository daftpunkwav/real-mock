import { latinLetterRatio } from "./audioRecorderPcm";
import type { SpeechRecognition, SpeechRecognitionEvent } from "./audioRecorderTypes";

/** Refs and callbacks shared by the ASR session and the recorder. */
interface AsrRefs {
  getSession: () => number;
  isCapturing: () => boolean;
  captureEnabledNow: () => boolean;
  asrAllowedRef: { current: boolean };
  recognitionRef: { current: SpeechRecognition | null };
  asrLangRef: { current: "zh-CN" | "en-US" };
  finalsRef: { current: string };
  interimRef: { current: string };
  lastFinalAtRef: { current: number };
  lastInterimUpdateRef: { current: number };
  setPartialText: (t: string) => void;
  onPartialRef: { current: ((t: string) => void) | undefined };
}

interface SpeechRecognitionSession {
  /** Allow and start recognition immediately. */
  enableAndStart: () => void;
  /** Enable recognition after the given arm delay. */
  startAfterArm: (delayMs: number) => void;
}

/**
 * Web Speech API session: starts recognition, folds finals/interim into the
 * partial text (interim updates refresh timestamps), and restarts itself from
 * onend while the session is still live. Language switches (zh/en by letter
 * ratio) recreate the recognizer; VAD and PCM capture stay independent of ASR.
 */
export function createSpeechRecognitionSession(refs: AsrRefs): SpeechRecognitionSession {
  const session = refs.getSession();

  let startRec: () => void = () => {};
  startRec = () => {
    if (session !== refs.getSession()) return;
    if (!refs.asrAllowedRef.current || !refs.isCapturing()) return;
    // Already started
    if (refs.recognitionRef.current) return;
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) return;
    const rec = new SR();
    rec.lang = refs.asrLangRef.current;
    rec.continuous = true;
    rec.interimResults = true;
    rec.onresult = (event: SpeechRecognitionEvent) => {
      if (!refs.isCapturing()) return;
      let interim = "";
      let gotFinal = false;
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const r = event.results[i];
        if (!r) continue;
        const piece = r[0]?.transcript ?? "";
        if (r.isFinal) {
          refs.finalsRef.current = `${refs.finalsRef.current}${piece}`;
          gotFinal = true;
        } else {
          interim += piece;
        }
      }
      refs.interimRef.current = interim;
      if (gotFinal) refs.lastFinalAtRef.current = Date.now();
      if (interim) refs.lastInterimUpdateRef.current = Date.now();
      const text = `${refs.finalsRef.current}${refs.interimRef.current}`.trim();
      refs.setPartialText(text);
      refs.onPartialRef.current?.(text);

      const tail = text.slice(-48);
      if (tail.length >= 3) {
        const ratio = latinLetterRatio(tail);
        const nextLang: "zh-CN" | "en-US" = ratio >= 0.55 ? "en-US" : "zh-CN";
        if (nextLang !== refs.asrLangRef.current) {
          refs.asrLangRef.current = nextLang;
          try {
            rec.onend = null;
            rec.stop();
          } catch {
            /* ignore */
          }
          refs.recognitionRef.current = null;
          window.setTimeout(() => {
            if (session !== refs.getSession()) return;
            try {
              startRec();
            } catch {
              /* ignore */
            }
          }, 80);
        }
      }
    };
    rec.onerror = () => {
      /* no-speech / aborted by onend */
    };
    rec.onend = () => {
      refs.recognitionRef.current = null;
      if (session !== refs.getSession()) return;
      if (!refs.asrAllowedRef.current || !refs.isCapturing()) return;
      try {
        startRec();
      } catch {
        /* ignore */
      }
    };
    try {
      rec.start();
      refs.recognitionRef.current = rec;
    } catch {
      /* already started */
    }
  };

  return {
    enableAndStart: () => {
      refs.asrAllowedRef.current = true;
      try {
        startRec();
      } catch {
        /* ignore */
      }
    },
    startAfterArm: (delayMs: number) => {
      window.setTimeout(() => {
        if (session !== refs.getSession()) return;
        if (!refs.captureEnabledNow()) return;
        refs.asrAllowedRef.current = true;
        try {
          startRec();
        } catch {
          /* ignore */
        }
      }, Math.max(0, delayMs));
    },
  };
}
