"use client";

import { useCallback, useEffect, useRef } from "react";
import type { Dispatch, SetStateAction } from "react";
import { getTranslator } from "@/i18n/resolve";
import { toast } from "@/components/Toast";
import type { ClientEvent, FaceAnalysis } from "@/types";
import { isLikelyEchoOfAssistant } from "../../echo";
import type { VideoPanelHandle } from "../../components/VideoPanel";
import type { AnyRef } from "./useInterviewRoomEvents";
import type { TurnTimerState } from "./useInterviewRoomState";

/** Bridge that lets callbacks defined before the recorder read its current state. */
export interface RecorderBridge {
  flush: () => void;
  isRecording: boolean;
  partialText: string;
  micError: string;
}

interface InterviewRoomActionsDeps {
  setInputText: Dispatch<SetStateAction<string>>;
  setAudioBlocked: Dispatch<SetStateAction<boolean>>;
  setShowOutline: Dispatch<SetStateAction<boolean>>;
  setFinishingUi: Dispatch<SetStateAction<boolean>>;
  turnStateRef: AnyRef<string>;
  bargeLockRef: AnyRef<boolean>;
  aiSpeakStartedAtRef: AnyRef<number>;
  lastAssistantTextRef: AnyRef<string>;
  partialTextRef: AnyRef<string>;
  sttThrottleRef: AnyRef<number>;
  finishingRef: AnyRef<boolean>;
  navigatingRef: AnyRef<boolean>;
  playbackGenRef: AnyRef<number>;
  expectedPlaybackGenRef: AnyRef<number>;
  localBargeStopRef: AnyRef<boolean>;
  lastPlaybackDoneGenRef: AnyRef<number | null>;
  showOutlineRef: AnyRef<boolean>;
  videoRef: AnyRef<VideoPanelHandle | null>;
  faceRef: AnyRef<FaceAnalysis>;
  seedCaptureFromRingRef: AnyRef<() => void>;
  bumpSilenceTimerRef: AnyRef<() => void>;
  setTurnTimer: Dispatch<SetStateAction<TurnTimerState>>;
  turnTimerRef: AnyRef<TurnTimerState>;
  answerWaitMsRef: AnyRef<number>;
  typingUplinkAtRef: AnyRef<number>;
  disarmSpeechWatch: () => void;
  sendRef: AnyRef<(p: ClientEvent) => boolean>;
  recorderRef: AnyRef<RecorderBridge>;
  send: (p: ClientEvent) => boolean;
  stopTTS: (opts?: { silent?: boolean }) => void;
  unlockAudio: () => Promise<boolean>;
  flushHeldQueue: () => boolean;
  retryLastFailed: () => boolean;
  requestHint: (question: string) => void;
  micEnabled: boolean;
  turnState: string;
  canInput: boolean;
  inputText: string;
  referenceHint: string;
  lastQuestion: string;
}

/** Build room actions for submission, interruption, silence, replay, and voice status. */
export function useInterviewRoomActions(deps: InterviewRoomActionsDeps) {
  const depsRef = useRef(deps);
  depsRef.current = deps;

  const { send, stopTTS, unlockAudio, flushHeldQueue, retryLastFailed } = deps;

  const submitUserMessageRef = useRef<(text: string, pcm?: string, sampleRate?: number) => void>(
    () => {},
  );

  const submitUserMessage = useCallback(
    (text: string, pcmBase64 = "", sampleRate = 16000) => {
      const d = depsRef.current;
      const trimmed = text.trim();
      if (!trimmed && !pcmBase64) return;
      const imageBase64 = d.videoRef.current?.captureFrame() ?? undefined;
      const payload = {
        text: trimmed,
        face_analysis: d.faceRef.current,
        image_base64: imageBase64,
      };
      if (pcmBase64) {
        const sr =
          Number.isFinite(sampleRate) && sampleRate >= 8000 && sampleRate <= 96000
            ? Math.round(sampleRate)
            : 16000;
        send({ type: "user_turn_end", pcm: pcmBase64, sample_rate: sr, ...payload });
      } else {
        send({ type: "user_text", ...payload });
      }
      d.partialTextRef.current = "";
    },
    [send],
  );

  useEffect(() => {
    submitUserMessageRef.current = submitUserMessage;
  }, [submitUserMessage]);

  const notifyUserActivity = useCallback(() => {
    const d = depsRef.current;
    if (d.turnStateRef.current !== "USER_SPEAKING") return;
    const now = Date.now();
    if (d.turnTimerRef.current.phase === "answer") {
      // Answer phase already running: throttle the typing uplink only.
      if (now - d.typingUplinkAtRef.current >= 4000) {
        d.typingUplinkAtRef.current = now;
        d.sendRef.current({ type: "user_typing" });
      }
      return;
    }
    // First input (typing or voice partial): the think window ends and the
    // answer window gets a fixed deadline from THIS moment.
    d.typingUplinkAtRef.current = now;
    d.sendRef.current({ type: "user_typing" });
    d.setTurnTimer({
      phase: "answer",
      endsAt: now + (d.answerWaitMsRef.current || 120_000),
    });
  }, []);

  const onSilenceStable = useCallback((pcm: string, partial: string, sampleRate = 16000) => {
    const d = depsRef.current;
    if (d.turnStateRef.current !== "USER_SPEAKING") return;
    const cleaned = (partial || "").trim();
    if (cleaned && isLikelyEchoOfAssistant(cleaned, d.lastAssistantTextRef.current)) {
      console.warn("Discarding probable echo STT text");
      return;
    }
    d.partialTextRef.current = partial;
    submitUserMessageRef.current(partial, pcm, sampleRate);
  }, []);

  const onPartialStable = useCallback((text: string) => {
    const d = depsRef.current;
    if (d.turnStateRef.current !== "USER_SPEAKING") return;
    if (isLikelyEchoOfAssistant(text, d.lastAssistantTextRef.current)) return;
    d.partialTextRef.current = text;
    notifyUserActivity();
    const now = Date.now();
    if (now - d.sttThrottleRef.current >= 500) {
      d.sttThrottleRef.current = now;
      d.sendRef.current({ type: "stt_text", text });
    }
    d.disarmSpeechWatch();
    d.bumpSilenceTimerRef.current();
  }, [notifyUserActivity]);

  const onSpeechActivity = useCallback(() => {
    const d = depsRef.current;
    if (d.turnStateRef.current !== "USER_SPEAKING") return;
    d.disarmSpeechWatch();
    d.bumpSilenceTimerRef.current();
  }, []);

  const onBargeCandidate = useCallback(() => {
    const d = depsRef.current;
    if (d.turnStateRef.current !== "AI_SPEAKING" || d.bargeLockRef.current) return;
    if (Date.now() - d.aiSpeakStartedAtRef.current < 900) return;
    d.disarmSpeechWatch();
    d.bargeLockRef.current = true;
    d.expectedPlaybackGenRef.current =
      Math.max(d.expectedPlaybackGenRef.current, d.playbackGenRef.current) + 1;
    d.playbackGenRef.current = d.expectedPlaybackGenRef.current;
    d.localBargeStopRef.current = true;
    d.lastPlaybackDoneGenRef.current = null;
    stopTTS();
    d.seedCaptureFromRingRef.current();
    d.sendRef.current({ type: "barge_in" });
    window.setTimeout(() => {
      d.bargeLockRef.current = false;
    }, 2500);
  }, [stopTTS]);

  const handleFaceAnalysis = useCallback(
    (analysis: FaceAnalysis) => {
      depsRef.current.faceRef.current = analysis;
      send({ type: "vision_update", face_analysis: analysis });
    },
    [send],
  );

  const handleEnableAudio = async () => {
    const t = getTranslator("interview");
    const ok = await unlockAudio();
    if (ok) {
      depsRef.current.setAudioBlocked(false);
      toast.success(t("room.toast.audioEnabled"));
      if (!flushHeldQueue()) {
        retryLastFailed();
      }
    } else {
      toast.error(t("room.toast.audioEnableFailed"));
    }
  };

  const handleSend = () => {
    const d = depsRef.current;
    if (!d.canInput) return;
    if (d.inputText.trim()) {
      submitUserMessage(d.inputText.trim());
      d.setInputText("");
    } else if (d.recorderRef.current.isRecording) {
      d.recorderRef.current.flush();
    }
  };

  const handleFinish = () => {
    const d = depsRef.current;
    if (d.finishingRef.current || d.navigatingRef.current) return;
    d.finishingRef.current = true;
    d.setFinishingUi(true);
    // A non-silent stop invokes onPlaybackDone; the explicit send would duplicate this generation.
    d.stopTTS({ silent: true });
    d.send({ type: "tts_playback_done", generation: d.playbackGenRef.current });
    const ok = d.send({ type: "request_finish" });
    if (!ok) {
      d.finishingRef.current = false;
      d.setFinishingUi(false);
      toast.error(getTranslator("interview")("room.toast.finishDisconnected"));
      return;
    }
    toast.success(getTranslator("interview")("room.toast.finishing"));
  };

  const handleOutlineChange = (checked: boolean) => {
    const d = depsRef.current;
    d.setShowOutline(checked);
    d.showOutlineRef.current = checked;
    // Hiding preserves the generated answer so reopening can display the cache.
    if (!checked) return;
    if (!d.referenceHint && d.lastQuestion) d.requestHint(d.lastQuestion);
  };

  /** Build the returned label after recorder state has been synchronized. */
  const buildVoiceStatus = () => {
    const d = depsRef.current;
    const rec = d.recorderRef.current;
    const t = getTranslator("interview");
    return rec.micError
      ? t("room.voice.error", { msg: rec.micError })
      : !d.micEnabled
        ? t("room.voice.waitingTurn")
        : d.turnState === "AI_SPEAKING"
          ? rec.partialText
            ? t("room.voice.bargeWithText", { text: rec.partialText })
            : t("room.voice.bargeHint")
          : rec.partialText
            ? t("room.voice.recognizing", { text: rec.partialText })
            : rec.isRecording
              ? t("room.voice.listening")
              : t("room.voice.startingMic");
  };

  return {
    submitUserMessage,
    notifyUserActivity,
    onSilenceStable,
    onPartialStable,
    onSpeechActivity,
    onBargeCandidate,
    handleFaceAnalysis,
    handleEnableAudio,
    handleSend,
    handleFinish,
    handleOutlineChange,
    buildVoiceStatus,
  };
}
