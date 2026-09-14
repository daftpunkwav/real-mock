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
    audioUnlocked,
  };
}
