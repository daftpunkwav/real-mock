"use client";

import { useEffect, useRef, useState } from "react";
import type { ChatMessage } from "@/lib/api/contract";
import type { ClientEvent, FaceAnalysis } from "@/types";
import type { VideoPanelHandle } from "../../components/VideoPanel";

/** Server-backed turn countdown shown in the left chat panel. */
export interface TurnTimerState {
  phase: "think" | "answer" | null;
  endsAt: number;
}

interface InterviewRoomStateDeps {
  sessionId: number;
  historySessionId: number | null;
  historyMessages: ChatMessage[];
  restoredPhase: string;
  lastAssistantContent: string;
  turnState: string;
  send: (p: ClientEvent) => boolean;
}

/** Shared room state and refs, including session resets and history restoration. */
export function useInterviewRoomState(deps: InterviewRoomStateDeps) {
  const {
    sessionId,
    historySessionId,
    historyMessages,
    restoredPhase,
    lastAssistantContent,
    turnState,
    send,
  } = deps;

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamingText, setStreamingText] = useState("");
  const [currentPhase, setCurrentPhase] = useState("");
  /** Agent-authored step title (plan mode); empty = resolve via phase i18n. */
  const [currentPhaseTitle, setCurrentPhaseTitle] = useState("");
  const [emotion, setEmotion] = useState("neutral");
  const [aiSpeaking, setAiSpeaking] = useState(false);
  const [audioLevel, setAudioLevel] = useState(0);
  const [audioBlocked, setAudioBlocked] = useState(false);
  const [sttFailUntil, setSttFailUntil] = useState(0);
  const [showOutline, setShowOutline] = useState(true);
  const [tokenUsage, setTokenUsage] = useState(0);
  const [inputText, setInputText] = useState("");
  const [referenceHint, setReferenceHint] = useState("");
  const [hintLoading, setHintLoading] = useState(false);
  const [lastQuestion, setLastQuestion] = useState("");
  const [finishingUi, setFinishingUi] = useState(false);
  const [lastSources, setLastSources] = useState<string[]>([]);
  const [turnTimer, setTurnTimer] = useState<TurnTimerState>({ phase: null, endsAt: 0 });

  const hintTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const videoRef = useRef<VideoPanelHandle>(null);
  const faceRef = useRef<FaceAnalysis>({});
  const partialTextRef = useRef("");
  const bumpSilenceTimerRef = useRef<() => void>(() => {});
  const turnStateRef = useRef<string>("IDLE");
  const bargeLockRef = useRef(false);
  const aiSpeakStartedAtRef = useRef(0);
  const lastAssistantTextRef = useRef("");
  const clearCaptureBuffersRef = useRef<() => void>(() => {});
  const seedCaptureFromRingRef = useRef<() => void>(() => {});
  const sttThrottleRef = useRef(0);
  const finishingRef = useRef(false);
  const navigatingRef = useRef(false);
  const playbackGenRef = useRef(0);
  const expectedPlaybackGenRef = useRef(0);
  const localBargeStopRef = useRef(false);
  const lastPlaybackDoneGenRef = useRef<number | null>(null);
  /** Server-provided response window in milliseconds; 0 uses the default. */
  const waitMsRef = useRef(0);
  /** Server-provided answer window in milliseconds (first input → deadline); 0 uses the default. */
  const answerWaitMsRef = useRef(0);
  /** Live mirror of turnTimer for callbacks that must not re-bind. */
  const turnTimerRef = useRef<TurnTimerState>({ phase: null, endsAt: 0 });
  /** Last `user_typing` uplink (typing is continuous; the uplink is throttled). */
  const typingUplinkAtRef = useRef(0);
  /** True while the silence timer waits for the interviewer's speech to end
   * (playback done) instead of starting at text-complete. */
  const awaitingSpeechEndRef = useRef(false);
  /** Fallback bump when speech-end never arrives (text-only / TTS failed). */
  const speechFallbackRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const showOutlineRef = useRef(showOutline);
  const sendRef = useRef<(p: ClientEvent) => boolean>(() => false);

  /** Reset session-scoped state and refs when sessionId changes. */
  useEffect(() => {
    if (hintTimeoutRef.current) {
      clearTimeout(hintTimeoutRef.current);
      hintTimeoutRef.current = null;
    }
    if (speechFallbackRef.current) {
      clearTimeout(speechFallbackRef.current);
      speechFallbackRef.current = null;
    }
    awaitingSpeechEndRef.current = false;
    setStreamingText("");
    setFinishingUi(false);
    setTokenUsage(0);
    setInputText("");
    setReferenceHint("");
    setHintLoading(false);
    setLastQuestion("");
    setLastSources([]);
    setMessages([]);
    setCurrentPhase("");
    setCurrentPhaseTitle("");
    setTurnTimer({ phase: null, endsAt: 0 });
    answerWaitMsRef.current = 0;
    typingUplinkAtRef.current = 0;
    finishingRef.current = false;
    navigatingRef.current = false;
    playbackGenRef.current = 0;
    expectedPlaybackGenRef.current = 0;
    lastPlaybackDoneGenRef.current = null;
    lastAssistantTextRef.current = "";
  }, [sessionId]);

  /** Restore messages and the latest interviewer text for a previously loaded session. */
  useEffect(() => {
    if (historySessionId !== sessionId) return;
    if (historyMessages.length > 0) {
      setMessages(historyMessages);
      const chars = historyMessages
        .filter((m) => m.role === "assistant")
        .reduce((n, m) => n + m.content.length, 0);
      setTokenUsage(chars);
    }
    if (restoredPhase) setCurrentPhase(restoredPhase);
    if (lastAssistantContent) {
      lastAssistantTextRef.current = lastAssistantContent;
      setLastQuestion(lastAssistantContent);
    }
  }, [historySessionId, sessionId, historyMessages, restoredPhase, lastAssistantContent]);

  useEffect(() => {
    showOutlineRef.current = showOutline;
    sendRef.current = send;
  }, [showOutline, send]);

  useEffect(() => {
    turnTimerRef.current = turnTimer;
  }, [turnTimer]);

  useEffect(() => {
    turnStateRef.current = turnState;
    if (turnState === "AI_SPEAKING") {
      aiSpeakStartedAtRef.current = Date.now();
    }
  }, [turnState]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText]);

  return {
    state: {
      messages,
      streamingText,
      currentPhase,
      currentPhaseTitle,
      emotion,
      aiSpeaking,
      audioLevel,
      audioBlocked,
      sttFailUntil,
      showOutline,
      tokenUsage,
      inputText,
      referenceHint,
      hintLoading,
      lastQuestion,
      finishingUi,
      lastSources,
      turnTimer,
    },
    set: {
      setMessages,
      setStreamingText,
      setCurrentPhase,
      setCurrentPhaseTitle,
      setEmotion,
      setAiSpeaking,
      setAudioLevel,
      setAudioBlocked,
      setSttFailUntil,
      setShowOutline,
      setTokenUsage,
      setInputText,
      setReferenceHint,
      setHintLoading,
      setLastQuestion,
      setFinishingUi,
      setLastSources,
      setTurnTimer,
    },
    refs: {
      hintTimeoutRef,
      videoRef,
      faceRef,
      partialTextRef,
      bumpSilenceTimerRef,
      turnStateRef,
      bargeLockRef,
      aiSpeakStartedAtRef,
      lastAssistantTextRef,
      clearCaptureBuffersRef,
      seedCaptureFromRingRef,
      sttThrottleRef,
      finishingRef,
      navigatingRef,
      playbackGenRef,
      expectedPlaybackGenRef,
      localBargeStopRef,
      lastPlaybackDoneGenRef,
      waitMsRef,
      answerWaitMsRef,
      turnTimerRef,
      typingUplinkAtRef,
      awaitingSpeechEndRef,
      speechFallbackRef,
      chatEndRef,
      showOutlineRef,
      sendRef,
    },
  };
}
