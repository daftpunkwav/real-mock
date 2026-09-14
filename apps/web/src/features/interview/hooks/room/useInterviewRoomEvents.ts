"use client";

import { useCallback, useEffect, useRef } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { useRouter } from "next/navigation";
import { getTranslator } from "@/i18n/resolve";
import { toast } from "@/components/Toast";
import type { ChatMessage } from "@/lib/api/contract";
import type { ClientEvent, ServerEvent } from "@/types";

/** Minimal writable-ref shape compatible with React 18 and 19 useRef results. */
export type AnyRef<T> = { current: T };

interface InterviewRoomEventsDeps {
  setStreamingText: Dispatch<SetStateAction<string>>;
  setMessages: Dispatch<SetStateAction<ChatMessage[]>>;
  setCurrentPhase: Dispatch<SetStateAction<string>>;
  setCurrentPhaseTitle: Dispatch<SetStateAction<string>>;
  setEmotion: Dispatch<SetStateAction<string>>;
  setTokenUsage: Dispatch<SetStateAction<number>>;
  setAudioBlocked: Dispatch<SetStateAction<boolean>>;
  setHintLoading: Dispatch<SetStateAction<boolean>>;
  setReferenceHint: Dispatch<SetStateAction<string>>;
  setLastQuestion: Dispatch<SetStateAction<string>>;
  setFinishingUi: Dispatch<SetStateAction<boolean>>;
  setSttFailUntil: Dispatch<SetStateAction<number>>;
  setLastSources: Dispatch<SetStateAction<string[]>>;
  playbackGenRef: AnyRef<number>;
  expectedPlaybackGenRef: AnyRef<number>;
  lastPlaybackDoneGenRef: AnyRef<number | null>;
  localBargeStopRef: AnyRef<boolean>;
  waitMsRef: AnyRef<number>;
  lastAssistantTextRef: AnyRef<string>;
  hintTimeoutRef: AnyRef<ReturnType<typeof setTimeout> | null>;
  finishingRef: AnyRef<boolean>;
  navigatingRef: AnyRef<boolean>;
  bumpSilenceTimerRef: AnyRef<() => void>;
  sendRef: AnyRef<(p: ClientEvent) => boolean>;
  showOutlineRef: AnyRef<boolean>;
  on: <K extends ServerEvent["type"]>(
    type: K,
    handler: (msg: Extract<ServerEvent, { type: K }>) => void,
  ) => void;
  playBase64Mp3: (data: string) => void;
  stopTTS: (opts?: { silent?: boolean }) => void;
  router: ReturnType<typeof useRouter>;
  sessionId: number;
}

/**
 * Registers room WebSocket handlers for assistant, TTS, STT, hints, phases,
 * completion, info, and errors. Playback refs, TTS, and routing are injected
 * so this hook owns event orchestration without duplicating their internals.
 */
export function useInterviewRoomEvents(deps: InterviewRoomEventsDeps) {
  const depsRef = useRef(deps);
  depsRef.current = deps;

  const clearHintTimeout = useCallback(() => {
    const ref = depsRef.current.hintTimeoutRef;
    if (ref.current) {
      clearTimeout(ref.current);
      ref.current = null;
    }
  }, []);

  const requestHint = useCallback(
    (question: string) => {
      const d = depsRef.current;
      if (!d.showOutlineRef.current || !question.trim()) return;
      d.setHintLoading(true);
      d.setReferenceHint("");
      d.setLastQuestion(question);
      clearHintTimeout();
      d.hintTimeoutRef.current = setTimeout(() => {
        d.setHintLoading(false);
        d.setReferenceHint((prev) =>
          prev.trim()
            ? prev
            : getTranslator("interview")("room.hint.timeout"),
        );
      }, 25_000);
      d.sendRef.current({ type: "request_hint", question });
    },
    [clearHintTimeout],
  );

  useEffect(() => () => clearHintTimeout(), [clearHintTimeout]);

  const { on, playBase64Mp3, router, sessionId, stopTTS } = deps;

  useEffect(() => {
    const d = depsRef.current;

    const announceVerdict = (result?: string | null) => {
      if (result !== "passed" && result !== "failed") return;
      const t = getTranslator("interview");
      if (result === "passed") {
        toast.success(t("room.verdict.passed"));
      } else {
        toast.error(t("room.verdict.failed"));
      }
    };

    const finishOnceAndNavigate = async () => {
      if (d.navigatingRef.current) return;
      d.navigatingRef.current = true;
      d.finishingRef.current = true;
      d.setFinishingUi(true);
      // A non-silent stop invokes onPlaybackDone; the explicit send would duplicate this generation.
      d.stopTTS({ silent: true });
      d.sendRef.current({
        type: "tts_playback_done",
        generation: d.playbackGenRef.current,
      });
      d.router.push(`/report/${d.sessionId}`);
    };

    on("assistant_token", (msg) => d.setStreamingText((prev) => prev + msg.token));

    on("assistant_done", (msg) => {
      d.setMessages((prev) => [...prev, { role: "assistant", content: msg.content }]);
      d.setStreamingText("");
      d.setCurrentPhase(msg.phase);
      d.setCurrentPhaseTitle(msg.phase_title || "");
      d.setEmotion(msg.emotion || "neutral");
      d.setTokenUsage((t) => t + msg.content.length);
      d.lastAssistantTextRef.current = msg.content || "";
      d.setLastSources(Array.isArray(msg.sources) ? msg.sources : []);
      if (typeof msg.playback_generation === "number") {
        d.playbackGenRef.current = msg.playback_generation;
        d.expectedPlaybackGenRef.current = Math.max(
          d.expectedPlaybackGenRef.current,
          msg.playback_generation,
        );
      }
      // Use the server estimate to tailor the silence timer to the question.
      if (typeof msg.wait_seconds === "number" && msg.wait_seconds > 0) {
        d.waitMsRef.current = Math.min(120, Math.max(15, msg.wait_seconds)) * 1000;
        d.bumpSilenceTimerRef.current();
      }
      if (!msg.is_complete) {
        requestHint(msg.content);
      }
      if (msg.is_complete) {
        announceVerdict(msg.result);
        void finishOnceAndNavigate();
      }
    });

    on("stt_final", (msg) => {
      if (msg.text) d.setMessages((prev) => [...prev, { role: "user", content: msg.text }]);
    });

    on("tts_audio", (msg) => {
      const gen = msg.playback_generation;
      if (typeof gen === "number") {
        if (gen < d.expectedPlaybackGenRef.current) {
          return;
        }
        d.playbackGenRef.current = gen;
        d.expectedPlaybackGenRef.current = Math.max(d.expectedPlaybackGenRef.current, gen);
      }
      playBase64Mp3(msg.data);
    });

    on("tts_failed", (msg) => {
      d.setAudioBlocked(true);
      toast.error(msg.message || getTranslator("interview")("room.toast.ttsFailed"));
      d.setMessages((prev) => [...prev, { role: "assistant", content: getTranslator("interview")("room.msg.warning", { msg: msg.message }) }]);
      d.sendRef.current({
        type: "tts_playback_done",
        generation: d.playbackGenRef.current,
      });
    });

    on("tts_interrupted", (msg) => {
      if (typeof msg.playback_generation === "number") {
        d.expectedPlaybackGenRef.current = Math.max(
          d.expectedPlaybackGenRef.current,
          msg.playback_generation,
        );
        d.playbackGenRef.current = d.expectedPlaybackGenRef.current;
      }
      if (d.localBargeStopRef.current) {
        d.localBargeStopRef.current = false;
        d.stopTTS({ silent: true });
      } else {
        d.expectedPlaybackGenRef.current =
          Math.max(d.expectedPlaybackGenRef.current, d.playbackGenRef.current) + 1;
        d.playbackGenRef.current = d.expectedPlaybackGenRef.current;
        d.lastPlaybackDoneGenRef.current = null;
        d.stopTTS();
      }
      const n = msg.candidate_interrupts;
      toast.info(
        typeof n === "number"
          ? getTranslator("interview")("room.toast.interruptedCount", { n })
          : getTranslator("interview")("room.toast.interrupted"),
      );
    });

    on("silence_nudge", (msg) => {
      // Show LLM silence nudges as normal interviewer lines (no hint prefix)
      d.setMessages((prev) => [...prev, { role: "assistant", content: msg.content }]);
      d.lastAssistantTextRef.current = msg.content || "";
    });

    on("reference_hint_loading", () => d.setHintLoading(true));

    on("reference_hint", (msg) => {
      const cleaned = msg.content
        .replace(/<think>[\s\S]*?<\/think>/gi, "")
        .replace(/<thinking>[\s\S]*?<\/thinking>/gi, "")
        .trim();
      clearHintTimeout();
      d.setReferenceHint(cleaned);
      d.setLastQuestion(msg.question || "");
      d.setHintLoading(false);
    });

    on("phase_changed", (msg) => {
      if (msg.phase) d.setCurrentPhase(msg.phase);
      d.setCurrentPhaseTitle(msg.phase_title || "");
    });

    on("interview_complete", (msg) => {
      announceVerdict(msg.result);
      void finishOnceAndNavigate();
    });

    on("info", (msg) => {
      if (msg.message) toast.info(String(msg.message));
    });

    on("error", (msg) => {
      d.setMessages((prev) => [...prev, { role: "assistant", content: getTranslator("interview")("room.msg.warning", { msg: msg.message }) }]);
      // Reset finish UI whenever an error arrives mid-finish (do not substring-match backend copy)
      if (d.finishingRef.current) {
        d.finishingRef.current = false;
        d.setFinishingUi(false);
      }
      const text = String(msg.message ?? "");
      const code = msg.code ?? "";
      // Prefer WS error codes; bilingual substrings cover older frames / raw messages
      const sttFail = code === "C2001" || /未能识别|Could not recognize/i.test(text);
      const ttsFail =
        code === "C2002" || /语音合成失败|Speech synthesis failed|合成失败/i.test(text);
      if (sttFail || ttsFail) {
        d.setSttFailUntil(Date.now() + 18_000);
        if (ttsFail || /语音合成|synthesis/i.test(text)) {
          d.setAudioBlocked(true);
        }
        if (sttFail) {
          toast.error(getTranslator("interview")("room.toast.sttFailed"));
        }
      }
    });
  }, [on, playBase64Mp3, router, sessionId, requestHint, stopTTS, clearHintTimeout]);

  return { requestHint, clearHintTimeout };
}
