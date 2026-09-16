"use client";

import { useCallback, useEffect, useRef } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { useRouter } from "next/navigation";
import { getTranslator } from "@/i18n/resolve";
import { toast } from "@/components/Toast";
import type { ChatMessage } from "@/lib/api/contract";
import type { ClientEvent, ServerEvent } from "@/types";
import type { TurnTimerState } from "./useInterviewRoomState";

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
  setTurnTimer: Dispatch<SetStateAction<TurnTimerState>>;
  playbackGenRef: AnyRef<number>;
  expectedPlaybackGenRef: AnyRef<number>;
  lastPlaybackDoneGenRef: AnyRef<number | null>;
  localBargeStopRef: AnyRef<boolean>;
  waitMsRef: AnyRef<number>;
  answerWaitMsRef: AnyRef<number>;
  turnTimerRef: AnyRef<TurnTimerState>;
  lastAssistantTextRef: AnyRef<string>;
  hintTimeoutRef: AnyRef<ReturnType<typeof setTimeout> | null>;
  awaitingSpeechEndRef: AnyRef<boolean>;
  speechFallbackRef: AnyRef<ReturnType<typeof setTimeout> | null>;
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
  /** True while closing TTS audio is queued or speaking (excludes held audio). */
  isActivelyPlaying?: () => boolean;
  router: ReturnType<typeof useRouter>;
  sessionId: number;
}

/**
 * Registers room WebSocket handlers for assistant, TTS, STT, hints, phases,
 * completion, info, and errors. Playback refs, TTS, and routing are injected
 * so this hook owns event orchestration without duplicating their internals.
 * Closing completion waits for the spoken wrap-up to drain before navigating
 * to the report (text-complete is not speech-complete).
 */
export function useInterviewRoomEvents(deps: InterviewRoomEventsDeps) {
  const depsRef = useRef(deps);
  depsRef.current = deps;
  /**
   * False after unmount: the closing-navigation wait must not push a route on
   * a dead room (e.g. the candidate pressed back while the wrap-up played).
   * Reset on every (re)subscription so StrictMode remounts keep working.
   */
  const mountedRef = useRef(true);

  const clearHintTimeout = useCallback(() => {
    const ref = depsRef.current.hintTimeoutRef;
    if (ref.current) {
      clearTimeout(ref.current);
      ref.current = null;
    }
  }, []);

  /** Cancel the speech-end watch (user active / turn over / session reset). */
  const disarmSpeechWatch = useCallback(() => {
    const d = depsRef.current;
    d.awaitingSpeechEndRef.current = false;
    if (d.speechFallbackRef.current) {
      clearTimeout(d.speechFallbackRef.current);
      d.speechFallbackRef.current = null;
    }
  }, []);

  /** Fire the silence timer now that the interviewer's speech has ended. */
  const fireSpeechEndBump = useCallback(() => {
    const d = depsRef.current;
    if (!d.awaitingSpeechEndRef.current) return;
    disarmSpeechWatch();
    d.bumpSilenceTimerRef.current();
  }, [disarmSpeechWatch]);

  /** Watch for speech-end, then start the silence timer (text-complete is NOT the anchor). */
  const armSpeechWatch = useCallback(() => {
    const d = depsRef.current;
    d.awaitingSpeechEndRef.current = true;
    if (d.speechFallbackRef.current) clearTimeout(d.speechFallbackRef.current);
    // Fallback for turns with no speech-end signal (text-only / TTS failed):
    // cancelled by the real playback-done on audio turns.
    d.speechFallbackRef.current = setTimeout(
      () => fireSpeechEndBump(),
      (d.waitMsRef.current || 10_000) + 5_000,
    );
  }, [fireSpeechEndBump]);

  const requestHint = useCallback(
    (question: string) => {
      const d = depsRef.current;
      if (!d.showOutlineRef.current || !question.trim()) return;
      d.setHintLoading(true);
      d.setReferenceHint("");
      d.setLastQuestion(question);
      clearHintTimeout();
      // Outline resolves in seconds; detailed (agent-loop) mode gets a longer
      // budget — the server re-announces loading with the mode on every path.
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

  useEffect(
    () => () => {
      clearHintTimeout();
      disarmSpeechWatch();
    },
    [clearHintTimeout, disarmSpeechWatch],
  );

  const { on, playBase64Mp3, router, sessionId, stopTTS } = deps;

  useEffect(() => {
    mountedRef.current = true;
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

    /**
     * Closing navigation: wait for the spoken wrap-up to finish playing before
     * leaving the room. `assistant_done(is_complete)` is text-complete, NOT
     * speech-complete — trailing `tts_audio` frames are still being synthesized
     * in the background. Navigating immediately (plus `stopTTS(silent)`) drops
     * the remaining sentences and closes the WS, so the candidate never hears
     * the full comment.
     */
    const scheduleFinishNavigation = () => {
      if (d.navigatingRef.current) return;
      d.navigatingRef.current = true;
      d.finishingRef.current = true;
      d.setFinishingUi(true);
      disarmSpeechWatch();
      try {
        toast.info(getTranslator("interview")("room.finish.playingClosing"));
      } catch {
        /* toast best-effort */
      }
      // Do NOT stop TTS here: let the closing speech keep playing. The natural
      // onPlaybackDone callback reports `tts_playback_done` when the queue
      // drains; a premature explicit send would unblock the backend wait early.
      void (async () => {
        const MIN_WAIT_MS = 3000; // allow trailing tts_audio to arrive/synthesize
        const MAX_WAIT_MS = 40000; // fallback so a stuck queue never pins the room
        const STABLE_MS = 1000; // idle-stable window before leaving
        const POLL_MS = 300;
        const start = Date.now();
        await new Promise((r) => setTimeout(r, MIN_WAIT_MS));
        let idleSince: number | null = null;
        while (Date.now() - start < MAX_WAIT_MS) {
          // Read live deps via depsRef: `d` is the effect-mount snapshot and
          // `isActivelyPlaying` identity may be stale across re-renders.
          const live = depsRef.current;
          let busy = false;
          try {
            busy = live.isActivelyPlaying?.() ?? false;
          } catch {
            busy = false;
          }
          if (busy) {
            idleSince = null;
          } else {
            if (idleSince === null) idleSince = Date.now();
            if (Date.now() - idleSince >= STABLE_MS) break;
          }
          await new Promise((r) => setTimeout(r, POLL_MS));
        }
        if (!mountedRef.current) return;
        try {
          const live = depsRef.current;
          live.router.push(`/report/${live.sessionId}`);
        } catch {
          /* navigation best-effort; WS cleanup handles the rest */
        }
      })();
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
      // Use the server estimate to tailor the silence timer to the question
      // (7-60s window, set by the interviewer's personality/strictness/style
      // and question difficulty). The timer itself starts when the
      // interviewer's SPEECH ends, not here at text-complete.
      if (typeof msg.wait_seconds === "number" && msg.wait_seconds > 0) {
        d.waitMsRef.current = Math.min(60, Math.max(7, msg.wait_seconds)) * 1000;
      }
      // Answer window (server clamps 90-300s): counts from the candidate's
      // FIRST input, displayed as 作答时间 in the chat panel.
      if (typeof msg.answer_wait_seconds === "number" && msg.answer_wait_seconds > 0) {
        d.answerWaitMsRef.current = Math.min(300, Math.max(90, msg.answer_wait_seconds)) * 1000;
      }
      // Think countdown starts at text-complete; the phase flips to "answer"
      // on the candidate's first input (see notifyUserActivity).
      d.setTurnTimer(
        msg.is_complete
          ? { phase: null, endsAt: 0 }
          : { phase: "think", endsAt: Date.now() + (d.waitMsRef.current || 25_000) },
      );
      armSpeechWatch();
      if (!msg.is_complete) {
        requestHint(msg.content);
      }
      if (msg.is_complete) {
        announceVerdict(msg.result);
        scheduleFinishNavigation();
      }
    });

    on("stt_final", (msg) => {
      if (msg.text) d.setMessages((prev) => [...prev, { role: "user", content: msg.text }]);
      // The answer was submitted: both countdowns are done for this round.
      d.setTurnTimer({ phase: null, endsAt: 0 });
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
      // No audio will play: speech is already "over", start the timer now.
      fireSpeechEndBump();
    });

    on("tts_interrupted", (msg) => {
      // Speech was cut off (usually the candidate barging in): the old watch
      // is stale; user activity re-arms the timer from here.
      disarmSpeechWatch();
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
      // A spoken probe re-opens the think countdown (the server re-arms its
      // timer too); an in-flight answer keeps its own deadline.
      if (d.turnTimerRef.current.phase !== "answer") {
        d.setTurnTimer({ phase: "think", endsAt: Date.now() + (d.waitMsRef.current || 25_000) });
      }
      // A spoken probe restarts the watch: the next timer starts when THIS
      // probe's speech ends (drives probe 2 / the closing nudge).
      armSpeechWatch();
    });

    on("reference_hint_loading", (msg) => {
      d.setHintLoading(true);
      // The server announces the true budget: detailed (agent-loop) mode gets
      // 90s, outline keeps 25s. Reset the provisional timeout from requestHint.
      clearHintTimeout();
      const budgetMs = msg.detailed ? 90_000 : 25_000;
      d.hintTimeoutRef.current = setTimeout(() => {
        d.setHintLoading(false);
        d.setReferenceHint((prev) =>
          prev.trim()
            ? prev
            : getTranslator("interview")(
                msg.detailed ? "room.hint.timeoutDetailed" : "room.hint.timeout",
              ),
        );
      }, budgetMs);
    });

    on("reference_hint_error", (msg) => {
      // Terminal failure (e.g. rate-limited): resolve loading with the message.
      clearHintTimeout();
      d.setReferenceHint(msg.message || "");
      // Preserve the existing question if the error frame arrives malformed;
      // otherwise the re-generate button would become permanently disabled.
      d.setLastQuestion((prev) => msg.question || prev || "");
      d.setHintLoading(false);
    });

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
      d.setTurnTimer({ phase: null, endsAt: 0 });
      // Backend now delays this frame until client playback is done, so it is
      // a safe-to-navigate signal. If the assistant_done path already scheduled
      // the wait, this is a deduped no-op via navigatingRef.
      scheduleFinishNavigation();
    });

    on("info", (msg) => {
      if (msg.message) toast.info(String(msg.message));
    });

    on("error", (msg) => {
      d.setMessages((prev) => [...prev, { role: "assistant", content: getTranslator("interview")("room.msg.warning", { msg: msg.message }) }]);
      // Reset finish UI when closing fails so the candidate can retry. Once
      // navigation is scheduled (closing speech playing), errors must not pop
      // the finishing UI back to the End button.
      if (d.finishingRef.current && !d.navigatingRef.current) {
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

    return () => {
      mountedRef.current = false;
    };
  }, [on, playBase64Mp3, router, sessionId, requestHint, stopTTS, clearHintTimeout, armSpeechWatch, disarmSpeechWatch, fireSpeechEndBump]);

  return { requestHint, clearHintTimeout, fireSpeechEndBump, disarmSpeechWatch };
}
