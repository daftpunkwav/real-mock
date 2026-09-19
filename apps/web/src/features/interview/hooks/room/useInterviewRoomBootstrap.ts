"use client";

import { useEffect, useMemo, useState } from "react";
import type { ChatMessage } from "@/lib/api/contract";
import { resolvePhaseLabels } from "@/config/phases";
import { useLocale } from "@/i18n/localeContext";
import { interviewHttp as api } from "@/lib/api/clients";
import { toVisibleChatMessages } from "../../messages";

interface InterviewSessionMeta {
  avatar_id: string;
  scene_id: string;
  workflow_type: string;
}

const DEFAULT_META: InterviewSessionMeta = {
  avatar_id: "professional_male",
  scene_id: "meeting_room",
  workflow_type: "technical",
};

/** One agent-planned flow step (light projection from the session API). */
export type PlanStepView = { id: string; title: string };

/**
 * Loads room authentication state, history, phase labels, and silence-nudge
 * configuration. Live messages remain page-owned and arrive through WebSocket;
 * this hook provides only the initial snapshot for each session.
 */
export function useInterviewRoomBootstrap(sessionId: number) {
  const { locale } = useLocale();
  const sessionIdValid = Number.isFinite(sessionId) && sessionId > 0;
  const [tokenMissing, setTokenMissing] = useState(false);
  const [sessionMeta, setSessionMeta] = useState<InterviewSessionMeta>(DEFAULT_META);
  const [historyMessages, setHistoryMessages] = useState<ChatMessage[]>([]);
  const [restoredPhase, setRestoredPhase] = useState("");
  const [sessionStatus, setSessionStatus] = useState("");
  const [silenceNudgeMs, setSilenceNudgeMs] = useState(25000);
  const [phaseLabelOverlay, setPhaseLabelOverlay] = useState<Record<string, string> | null>(
    null,
  );
  const [lastAssistantContent, setLastAssistantContent] = useState("");
  const [historySessionId, setHistorySessionId] = useState<number | null>(null);
  const [planSteps, setPlanSteps] = useState<PlanStepView[]>([]);

  const phaseLabels = useMemo(
    () => resolvePhaseLabels(phaseLabelOverlay, locale),
    [locale, phaseLabelOverlay],
  );

  useEffect(() => {
    if (!sessionIdValid) return;
    let cancelled = false;
    setTokenMissing(false);
    setHistoryMessages([]);
    setHistorySessionId(null);
    setRestoredPhase("");
    setSessionStatus("");
    setLastAssistantContent("");
    setSessionMeta(DEFAULT_META);
    setPhaseLabelOverlay(null);
    setPlanSteps([]);
    setSilenceNudgeMs(25000);

    const load = async () => {
      try {
        const session = await api.getSession(sessionId);
        if (cancelled) return;
        setTokenMissing(false);
        setSessionMeta({
          avatar_id: session.avatar_id || "professional_male",
          scene_id: session.scene_id || "meeting_room",
          workflow_type: session.workflow_type,
        });
        setRestoredPhase(session.current_phase || "");
        setSessionStatus(session.status || "");
        setPlanSteps(Array.isArray(session.plan) ? session.plan : []);
        void import("@/features/avatar").then((m) => {
          m.prefetchAvatar(session.avatar_id || "professional_male");
        });
      } catch (e) {
        if (cancelled) return;
        const status = e && typeof e === "object" && "status" in e ? Number(e.status) : 0;
        setTokenMissing(status === 403 || status === 401);
        return;
      }

      try {
        const raw = await api.getMessages(sessionId);
        if (cancelled) return;
        const visible = toVisibleChatMessages(raw);
        setHistoryMessages(visible);
        const lastAsst = [...visible].reverse().find((m) => m.role === "assistant");
        setLastAssistantContent(lastAsst?.content || "");
        setHistorySessionId(sessionId);
      } catch {
        if (!cancelled) {
          setHistoryMessages([]);
          setHistorySessionId(sessionId);
        }
      }

      try {
        const opts = await api.getOptions();
        if (cancelled) return;
        if (typeof opts.silence_nudge_seconds === "number" && opts.silence_nudge_seconds > 0) {
          setSilenceNudgeMs(opts.silence_nudge_seconds * 1000);
        }
        if (opts.phase_labels) {
          setPhaseLabelOverlay(opts.phase_labels);
        }
      } catch {
        /* Offline fallback: resolvePhaseLabels uses i18n catalog */
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, [sessionId, sessionIdValid]);

  return {
    sessionIdValid,
    tokenMissing,
    sessionMeta,
    historyMessages,
    restoredPhase,
    sessionStatus,
    silenceNudgeMs,
    phaseLabels,
    lastAssistantContent,
    historySessionId,
    planSteps,
  };
}
