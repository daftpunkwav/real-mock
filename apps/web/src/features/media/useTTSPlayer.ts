"use client";

import { useCallback, useRef, useState } from "react";
import { createAudioContext, ensureContextRunning, fireSilentProbe } from "./ttsAudio";
import { useTTSPlayerPlayback } from "./useTTSPlayerPlayback";

/** TTS player facade: unlock handling plus callback setters over useTTSPlayerPlayback. */
export function useTTSPlayer() {
  const onSpeakingChangeRef = useRef<(v: boolean) => void>(() => {});
  const onLevelRef = useRef<(level: number) => void>(() => {});
  const onBlockedRef = useRef<(blocked: boolean) => void>(() => {});
  const onPlaybackDoneRef = useRef<() => void>(() => {});
  const [audioUnlocked, setAudioUnlocked] = useState(false);

  const playback = useTTSPlayerPlayback({
    onSpeakingChangeRef,
    onLevelRef,
    onBlockedRef,
    onPlaybackDoneRef,
  });

  const setOnSpeakingChange = useCallback((fn: (v: boolean) => void) => {
    onSpeakingChangeRef.current = fn;
  }, []);

  const setOnAudioLevel = useCallback((fn: (level: number) => void) => {
    onLevelRef.current = fn;
  }, []);

  const setOnPlaybackBlocked = useCallback((fn: (blocked: boolean) => void) => {
    onBlockedRef.current = fn;
  }, []);

  const setOnPlaybackDone = useCallback((fn: () => void) => {
    onPlaybackDoneRef.current = fn;
  }, []);

  /** Unlock audio on user gesture; returns true when playback is allowed. */
  const unlockAudio = useCallback(async () => {
    try {
      if (!playback.audioCtxRef.current) {
        playback.audioCtxRef.current = createAudioContext();
      }
      const ctx = playback.audioCtxRef.current;
      if (!ctx || !(await ensureContextRunning(ctx))) {
        playback.unlockedRef.current = false;
        setAudioUnlocked(false);
        onBlockedRef.current(true);
        return false;
      }
      fireSilentProbe(ctx);
      playback.unlockedRef.current = true;
      setAudioUnlocked(true);
      onBlockedRef.current(false);
      return true;
    } catch {
      playback.unlockedRef.current = false;
      setAudioUnlocked(false);
      onBlockedRef.current(true);
      return false;
    }
  }, [playback.audioCtxRef, playback.unlockedRef]);

  return {
    playBase64Mp3: playback.playBase64Mp3,
    setOnSpeakingChange,
    setOnAudioLevel,
    setOnPlaybackBlocked,
    setOnPlaybackDone,
    unlockAudio,
    retryLastFailed: playback.retryLastFailed,
    flushHeldQueue: playback.flushHeldQueue,
    stop: playback.stop,
    isSpeaking: playback.isSpeaking,
    isActivelyPlaying: playback.isActivelyPlaying,
    isQueueBusy: playback.isQueueBusy,
    queueDepth: playback.queueDepth,
    audioUnlocked,
    heldCount: playback.heldCount,
  };
}
