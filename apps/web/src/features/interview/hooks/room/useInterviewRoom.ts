"use client";

import { useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { useInterviewWS } from "./useInterviewWS";
import { useInterviewRoomBootstrap } from "./useInterviewRoomBootstrap";
import { useInterviewRoomState } from "./useInterviewRoomState";
import { useInterviewRoomTtsBinding } from "./useInterviewRoomTtsBinding";
import { useInterviewRoomEvents } from "./useInterviewRoomEvents";
import { useInterviewRoomActions, type RecorderBridge } from "./useInterviewRoomActions";
import { useInterviewRoomSilenceTimer } from "./useInterviewRoomSilenceTimer";
import { useInterviewRoomRecorderBridge } from "./useInterviewRoomRecorderBridge";

/**
 * Assemble room bootstrap, WebSocket, shared state, TTS, events, actions, and
 * recording into the model consumed by the page. Shared state and refs remain
 * centralized in useInterviewRoomState.
 */
export function useInterviewRoom(sessionId: number) {
  const router = useRouter();
  const bootstrap = useInterviewRoomBootstrap(sessionId);

  const { connected, everConnected, turnState, connectionState, reconnectAttempt, send, on, retryNow } =
    useInterviewWS(bootstrap.sessionIdValid ? sessionId : 0);

  const { state: st, set: setSt, refs: rf } = useInterviewRoomState({
    sessionId,
    historySessionId: bootstrap.historySessionId,
    historyMessages: bootstrap.historyMessages,
    restoredPhase: bootstrap.restoredPhase,
    lastAssistantContent: bootstrap.lastAssistantContent,
    turnState,
    send,
  });

  const { playBase64Mp3, unlockAudio, flushHeldQueue, retryLastFailed, stopTTS, audioUnlocked } =
    useInterviewRoomTtsBinding({
      playbackGenRef: rf.playbackGenRef,
      lastPlaybackDoneGenRef: rf.lastPlaybackDoneGenRef,
      sendRef: rf.sendRef,
      setAiSpeaking: setSt.setAiSpeaking,
      setAudioLevel: setSt.setAudioLevel,
      setAudioBlocked: setSt.setAudioBlocked,
    });

  const micEnabled =
    connected && (turnState === "USER_SPEAKING" || turnState === "AI_SPEAKING") && !st.finishingUi;
  // Voice capture stays muted while AI audio is still playing (the mic now opens
  // at text-complete, ahead of the playback): typing is available immediately,
  // but PCM capture waits so the speaker output is not transcribed as the user.
  const captureEnabled = turnState === "USER_SPEAKING" && !st.finishingUi && !st.aiSpeaking;
  const canInput = turnState === "USER_SPEAKING" && !st.finishingUi;

  useInterviewRoomSilenceTimer({
    micEnabled,
    sttFailUntil: st.sttFailUntil,
    silenceNudgeMs: bootstrap.silenceNudgeMs,
    waitMsRef: rf.waitMsRef,
    sendRef: rf.sendRef,
    bumpSilenceTimerRef: rf.bumpSilenceTimerRef,
  });

  const { requestHint } = useInterviewRoomEvents({
    setStreamingText: setSt.setStreamingText,
    setMessages: setSt.setMessages,
    setCurrentPhase: setSt.setCurrentPhase,
    setCurrentPhaseTitle: setSt.setCurrentPhaseTitle,
    setEmotion: setSt.setEmotion,
    setTokenUsage: setSt.setTokenUsage,
    setAudioBlocked: setSt.setAudioBlocked,
    setHintLoading: setSt.setHintLoading,
    setReferenceHint: setSt.setReferenceHint,
    setLastQuestion: setSt.setLastQuestion,
    setFinishingUi: setSt.setFinishingUi,
    setSttFailUntil: setSt.setSttFailUntil,
    setLastSources: setSt.setLastSources,
    playbackGenRef: rf.playbackGenRef,
    expectedPlaybackGenRef: rf.expectedPlaybackGenRef,
    lastPlaybackDoneGenRef: rf.lastPlaybackDoneGenRef,
    localBargeStopRef: rf.localBargeStopRef,
    waitMsRef: rf.waitMsRef,
    lastAssistantTextRef: rf.lastAssistantTextRef,
    hintTimeoutRef: rf.hintTimeoutRef,
    finishingRef: rf.finishingRef,
    navigatingRef: rf.navigatingRef,
    bumpSilenceTimerRef: rf.bumpSilenceTimerRef,
    sendRef: rf.sendRef,
    showOutlineRef: rf.showOutlineRef,
    on,
    playBase64Mp3,
    stopTTS,
    router,
    sessionId,
  });

  const recorderRef = useRef<RecorderBridge>({ flush: () => {}, isRecording: false, partialText: "", micError: "" });

  const actions = useInterviewRoomActions({
    setInputText: setSt.setInputText,
    setAudioBlocked: setSt.setAudioBlocked,
    setShowOutline: setSt.setShowOutline,
    setFinishingUi: setSt.setFinishingUi,
    turnStateRef: rf.turnStateRef,
    bargeLockRef: rf.bargeLockRef,
    aiSpeakStartedAtRef: rf.aiSpeakStartedAtRef,
    lastAssistantTextRef: rf.lastAssistantTextRef,
    partialTextRef: rf.partialTextRef,
    sttThrottleRef: rf.sttThrottleRef,
    finishingRef: rf.finishingRef,
    navigatingRef: rf.navigatingRef,
    playbackGenRef: rf.playbackGenRef,
    expectedPlaybackGenRef: rf.expectedPlaybackGenRef,
    localBargeStopRef: rf.localBargeStopRef,
    lastPlaybackDoneGenRef: rf.lastPlaybackDoneGenRef,
    showOutlineRef: rf.showOutlineRef,
    videoRef: rf.videoRef,
    faceRef: rf.faceRef,
    seedCaptureFromRingRef: rf.seedCaptureFromRingRef,
    bumpSilenceTimerRef: rf.bumpSilenceTimerRef,
    sendRef: rf.sendRef,
    recorderRef,
    send,
    stopTTS,
    unlockAudio,
    flushHeldQueue,
    retryLastFailed,
    requestHint,
    micEnabled,
    turnState,
    canInput,
    inputText: st.inputText,
    referenceHint: st.referenceHint,
    lastQuestion: st.lastQuestion,
  });

  const { isRecording } = useInterviewRoomRecorderBridge({
    micEnabled,
    captureEnabled,
    onSilenceStable: actions.onSilenceStable,
    onPartialStable: actions.onPartialStable,
    onSpeechActivity: actions.onSpeechActivity,
    onBargeCandidate: actions.onBargeCandidate,
    recorderRef,
    clearCaptureBuffersRef: rf.clearCaptureBuffersRef,
    seedCaptureFromRingRef: rf.seedCaptureFromRingRef,
  });

  const canSend = canInput && (Boolean(st.inputText.trim()) || isRecording);
  const goSetup = useCallback(() => {
    router.push("/interview");
  }, [router]);

  return {
    sessionId,
    sessionIdValid: bootstrap.sessionIdValid,
    tokenMissing: bootstrap.tokenMissing,
    goSetup,
    sessionMeta: bootstrap.sessionMeta,
    sessionStatus: bootstrap.sessionStatus,
    phaseLabels: bootstrap.phaseLabels,
    planSteps: bootstrap.planSteps,
    currentPhase: st.currentPhase,
    currentPhaseTitle: st.currentPhaseTitle,
    turnState,
    connected,
    everConnected,
    connectionState,
    reconnectAttempt,
    retryNow,
    messages: st.messages,
    streamingText: st.streamingText,
    chatEndRef: rf.chatEndRef,
    inputText: st.inputText,
    setInputText: setSt.setInputText,
    canInput,
    canSend,
    handleSend: actions.handleSend,
    handleFinish: actions.handleFinish,
    finishingUi: st.finishingUi,
    videoRef: rf.videoRef,
    isRecording,
    voiceStatus: actions.buildVoiceStatus(),
    handleFaceAnalysis: actions.handleFaceAnalysis,
    emotion: st.emotion,
    aiSpeaking: st.aiSpeaking,
    audioLevel: st.audioLevel,
    audioUnlocked,
    audioBlocked: st.audioBlocked,
    handleEnableAudio: actions.handleEnableAudio,
    showOutline: st.showOutline,
    handleOutlineChange: actions.handleOutlineChange,
    lastQuestion: st.lastQuestion,
    requestHint,
    hintLoading: st.hintLoading,
    referenceHint: st.referenceHint,
    lastSources: st.lastSources,
    tokenUsage: st.tokenUsage,
  };
}

export type InterviewRoomModel = ReturnType<typeof useInterviewRoom>;
