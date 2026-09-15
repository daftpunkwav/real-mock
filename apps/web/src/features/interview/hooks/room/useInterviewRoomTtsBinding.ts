"use client";

import { useEffect } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { ClientEvent } from "@/types";
import { useTTSPlayer } from "@/features/media";
import type { AnyRef } from "./useInterviewRoomEvents";

interface InterviewRoomTtsBindingDeps {
  playbackGenRef: AnyRef<number>;
  lastPlaybackDoneGenRef: AnyRef<number | null>;
  sendRef: AnyRef<(p: ClientEvent) => boolean>;
  bumpSilenceTimerRef: AnyRef<() => void>;
  awaitingSpeechEndRef: AnyRef<boolean>;
  speechFallbackRef: AnyRef<ReturnType<typeof setTimeout> | null>;
  setAiSpeaking: Dispatch<SetStateAction<boolean>>;
  setAudioLevel: Dispatch<SetStateAction<number>>;
  setAudioBlocked: Dispatch<SetStateAction<boolean>>;
}

/** Bind TTS callbacks with generation-guarded playback_done reporting. */
export function useInterviewRoomTtsBinding(deps: InterviewRoomTtsBindingDeps) {
  const {
    playBase64Mp3,
    setOnSpeakingChange,
    setOnAudioLevel,
    setOnPlaybackBlocked,
    setOnPlaybackDone,
    unlockAudio,
    flushHeldQueue,
    retryLastFailed,
    stop,
    isActivelyPlaying,
    audioUnlocked,
  } = useTTSPlayer();

  const { setAiSpeaking, setAudioLevel, setAudioBlocked } = deps;

  useEffect(() => {
    setOnSpeakingChange(setAiSpeaking);
    setOnAudioLevel(setAudioLevel);
    setOnPlaybackBlocked(setAudioBlocked);
    setOnPlaybackDone(() => {
      const g = deps.playbackGenRef.current;
      if (deps.lastPlaybackDoneGenRef.current === g) return;
      deps.lastPlaybackDoneGenRef.current = g;
      deps.sendRef.current({ type: "tts_playback_done", generation: g });
      // The interviewer's speech just ended: the silence timer starts now
      // (not at text-complete). No-op unless a turn armed the watch.
      if (deps.awaitingSpeechEndRef.current) {
        deps.awaitingSpeechEndRef.current = false;
        if (deps.speechFallbackRef.current) {
          clearTimeout(deps.speechFallbackRef.current);
          deps.speechFallbackRef.current = null;
        }
        deps.bumpSilenceTimerRef.current();
      }
    });
  }, [
    setOnSpeakingChange,
    setOnAudioLevel,
    setOnPlaybackBlocked,
    setOnPlaybackDone,
    setAiSpeaking,
    setAudioLevel,
    setAudioBlocked,
    deps.playbackGenRef,
    deps.lastPlaybackDoneGenRef,
    deps.sendRef,
    deps.bumpSilenceTimerRef,
    deps.awaitingSpeechEndRef,
    deps.speechFallbackRef,
  ]);

  useEffect(() => {
    return () => {
      stop();
    };
  }, [stop]);

  return {
    playBase64Mp3,
    unlockAudio,
    flushHeldQueue,
    retryLastFailed,
    stopTTS: stop,
    isActivelyPlaying,
    audioUnlocked,
  };
}
