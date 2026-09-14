"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  connectElementToAnalyser,
  createAnalyserNode,
  createAudioContext,
  ensureContextRunning,
} from "./ttsAudio";
import { createTTSLevelLoop, type TTSLevelLoop } from "./ttsLevelLoop";

/** Callback refs for speaking, level, blocked, and playback-done notifications. */
interface TTSPlayerCallbackRefs {
  onSpeakingChangeRef: { current: (v: boolean) => void };
  onLevelRef: { current: (level: number) => void };
  onBlockedRef: { current: (blocked: boolean) => void };
  onPlaybackDoneRef: { current: () => void };
}

interface TTSPlayerPlaybackApi {
  playBase64Mp3: (b64: string) => void;
  flushHeldQueue: () => boolean;
  retryLastFailed: () => boolean;
  stop: (opts?: { silent?: boolean }) => void;
  isSpeaking: () => boolean;
  isActivelyPlaying: () => boolean;
  isQueueBusy: () => boolean;
  queueDepth: number;
  heldCount: () => number;
  /** Shared AudioContext ref, created on unlock and reused for the analyser. */
  audioCtxRef: { current: AudioContext | null };
  unlockedRef: { current: boolean };
}

/**
 * Queued base64 MP3 playback with epoch cancellation and a held queue for locked audio.
 * Jobs chain on a promise queue; completion fires onPlaybackDone when idle.
 */
export function useTTSPlayerPlayback(callbacks: TTSPlayerCallbackRefs): TTSPlayerPlaybackApi {
  const { onSpeakingChangeRef, onLevelRef, onBlockedRef, onPlaybackDoneRef } = callbacks;
  const queueRef = useRef<Promise<void>>(Promise.resolve());
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const sourceNodeRef = useRef<MediaElementAudioSourceNode | null>(null);
  const speakingRef = useRef(false);
  const pendingCountRef = useRef(0);
  const unlockedRef = useRef(false);
  const epochRef = useRef(0);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  /** Payloads held while audio is locked, flushed after unlock. */
  const heldQueueRef = useRef<string[]>([]);
  const [queueDepth, setQueueDepth] = useState(0);

  const levelLoopRef = useRef<TTSLevelLoop | null>(null);
  if (levelLoopRef.current === null) {
    levelLoopRef.current = createTTSLevelLoop({
      getAnalyser: () => analyserRef.current,
      onLevel: (level) => onLevelRef.current(level),
    });
  }

  const _releaseCurrent = useCallback(() => {
    try {
      sourceNodeRef.current?.disconnect();
    } catch {
      /* noop */
    }
    sourceNodeRef.current = null;
    const a = currentAudioRef.current;
    if (!a) return;
    try {
      a.pause();
      a.src = "";
      a.onended = null;
      a.onerror = null;
    } catch {
      /* noop */
    }
    currentAudioRef.current = null;
  }, []);

  /** Fire onPlaybackDone when no pending jobs are speaking and no held items wait for unlock. */
  const _notifyIfIdle = useCallback(() => {
    if (pendingCountRef.current > 0 || speakingRef.current) return;
    if (!unlockedRef.current && heldQueueRef.current.length > 0) return;
    onPlaybackDoneRef.current();
  }, [onPlaybackDoneRef]);

  const playBase64Mp3 = useCallback(
    (b64: string) => {
      if (!b64) return;

      // Hold payloads until audio is unlocked; otherwise enqueue ordered playback.
      if (!unlockedRef.current) {
        heldQueueRef.current.push(b64);
        onBlockedRef.current(true);
        return;
      }

      const jobEpoch = epochRef.current;
      pendingCountRef.current += 1;
      setQueueDepth(pendingCountRef.current);
      const job = (prev: Promise<void>) =>
        prev.then(
          () =>
            new Promise<void>((resolve) => {
              const finishOk = () => {
                if (jobEpoch !== epochRef.current) {
                  resolve();
                  return;
                }
                pendingCountRef.current = Math.max(0, pendingCountRef.current - 1);
                setQueueDepth(pendingCountRef.current);
                currentAudioRef.current = null;
                speakingRef.current = false;
                onSpeakingChangeRef.current(false);
                levelLoopRef.current?.stop();
                _notifyIfIdle();
                resolve();
              };

              /** Requeue payload when playback is blocked and notify when idle. */
              const finishBlocked = () => {
                if (jobEpoch !== epochRef.current) {
                  resolve();
                  return;
                }
                pendingCountRef.current = Math.max(0, pendingCountRef.current - 1);
                setQueueDepth(pendingCountRef.current);
                currentAudioRef.current = null;
                speakingRef.current = false;
                onSpeakingChangeRef.current(false);
                levelLoopRef.current?.stop();
                heldQueueRef.current.push(b64);
                onBlockedRef.current(true);
                _notifyIfIdle();
                resolve();
              };

              if (jobEpoch !== epochRef.current) {
                resolve();
                return;
              }

              _releaseCurrent();
              const audio = new Audio(`data:audio/mpeg;base64,${b64}`);
              currentAudioRef.current = audio;
              speakingRef.current = true;
              onSpeakingChangeRef.current(true);

              const runPlay = async () => {
                try {
                  const ctx = audioCtxRef.current ?? createAudioContext();
                  if (ctx) {
                    audioCtxRef.current = ctx;
                    if (!(await ensureContextRunning(ctx))) {
                      finishBlocked();
                      return;
                    }
                    if (!analyserRef.current) {
                      analyserRef.current = createAnalyserNode(ctx);
                    }
                    const src = connectElementToAnalyser(ctx, audio, analyserRef.current);
                    if (src) {
                      sourceNodeRef.current = src;
                      levelLoopRef.current?.start();
                    }
                    /* Attach element source to analyser for level metering. */
                  }
                } catch {
                  /* Playback start failed; finish path reports it. */
                }

                audio.onended = () => {
                  finishOk();
                };
                audio.onerror = () => {
                  finishBlocked();
                };

                try {
                  await audio.play();
                  if (jobEpoch !== epochRef.current) {
                    try {
                      audio.pause();
                    } catch {
                      /* noop */
                    }
                    finishOk();
                    return;
                  }
                  onBlockedRef.current(false);
                } catch {
                  finishBlocked();
                }
              };

              void runPlay();
            }),
        );
      queueRef.current = job(queueRef.current);
    },
    [_releaseCurrent, _notifyIfIdle, onBlockedRef, onSpeakingChangeRef],
  );

  /** Flush held queue after unlock; returns false when empty. */
  const flushHeldQueue = useCallback(() => {
    const held = heldQueueRef.current.splice(0, heldQueueRef.current.length);
    if (held.length === 0) return false;
    onBlockedRef.current(false);
    for (const b64 of held) {
      playBase64Mp3(b64);
    }
    return true;
  }, [playBase64Mp3, onBlockedRef]);

  const retryLastFailed = useCallback(() => {
    return flushHeldQueue();
  }, [flushHeldQueue]);

  /**
   * Stop playback, clear queue and held items, and bump the epoch to cancel pending jobs.
   * @param opts.silent When true, skip the playback-done notification.
   */
  const stop = useCallback(
    (opts?: { silent?: boolean }) => {
      epochRef.current += 1;
      _releaseCurrent();
      speakingRef.current = false;
      pendingCountRef.current = 0;
      heldQueueRef.current = [];
      setQueueDepth(0);
      onSpeakingChangeRef.current(false);
      levelLoopRef.current?.stop();
      queueRef.current = Promise.resolve();
      if (!opts?.silent) {
        // Notify playback-done unless silenced.
        onPlaybackDoneRef.current();
      }
    },
    [_releaseCurrent, onPlaybackDoneRef, onSpeakingChangeRef],
  );

  useEffect(() => {
    return () => {
      stop();
      void audioCtxRef.current?.close().catch(() => {});
      audioCtxRef.current = null;
      analyserRef.current = null;
    };
  }, [stop]);

  return {
    playBase64Mp3,
    flushHeldQueue,
    retryLastFailed,
    stop,
    isSpeaking: () => speakingRef.current,
    /** True while a job is queued or audio is speaking (excludes held count; use heldCount()). */
    isActivelyPlaying: () => pendingCountRef.current > 0 || speakingRef.current,
    /** @deprecated Alias of isActivelyPlaying (neither includes held count; use heldCount()). */
    isQueueBusy: () => pendingCountRef.current > 0 || speakingRef.current,
    queueDepth,
    heldCount: () => heldQueueRef.current.length,
    audioCtxRef,
    unlockedRef,
  };
}
