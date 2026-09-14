"use client";

import { useT } from "@/i18n";
import { AlertTriangle, WifiOff } from "lucide-react";
import { VideoPanel } from "./VideoPanel";
import { InterviewRoomGate } from "./InterviewRoomGate";
import { InterviewRoomChrome } from "./InterviewRoomChrome";
import { InterviewRoomChat } from "./InterviewRoomChat";
import { InterviewRoomOutline } from "./InterviewRoomOutline";
import type { InterviewRoomModel } from "../hooks/room";

export function InterviewRoomView({ room }: { room: InterviewRoomModel }) {
  const {
    sessionIdValid,
    tokenMissing,
    goSetup,
    everConnected,
    connectionState,
    retryNow,
    videoRef,
    isRecording,
    voiceStatus,
    handleFaceAnalysis,
  } = room;
  const t = useT("interview");

  if (!sessionIdValid) {
    return (
      <InterviewRoomGate
        icon={<AlertTriangle size={24} />}
        title={t("room.gate.invalidSession.title")}
        desc={t("room.gate.invalidSession.desc")}
        tone="warning"
        onPrimary={goSetup}
        primaryLabel={t("room.gate.backToSetup")}
      />
    );
  }

  if (tokenMissing) {
    return (
      <InterviewRoomGate
        icon={<AlertTriangle size={24} />}
        title={t("room.gate.tokenMissing.title")}
        desc={t("room.gate.tokenMissing.desc")}
        tone="warning"
        onPrimary={goSetup}
        primaryLabel={t("room.gate.backToSetup")}
      />
    );
  }

  if (!everConnected && connectionState === "failed") {
    return (
      <InterviewRoomGate
        icon={<WifiOff size={24} />}
        title={t("room.gate.connectFailed.title")}
        desc={t("room.gate.connectFailed.desc")}
        tone="danger"
        onPrimary={retryNow}
        primaryLabel={t("room.gate.reconnect")}
        onSecondary={goSetup}
        secondaryLabel={t("room.gate.backToSetupShort")}
      />
    );
  }

  if (!everConnected && !room.connected) {
    return (
      <div className="h-screen flex flex-col items-center justify-center gap-3 bg-[var(--background)] text-ink-muted">
        <span className="block h-6 w-6 anim-spin rounded-full border-2 border-[var(--primary)] border-t-transparent" />
        <p className="text-[13px]">
          {connectionState === "reconnecting" ? t("room.connecting.reconnecting") : t("room.connecting.connecting")}
        </p>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-[var(--background)] text-[var(--foreground)] relative">
      <InterviewRoomChrome room={room} />
      <div className="flex-1 grid grid-cols-1 lg:grid-cols-[minmax(280px,1fr)_minmax(0,1.8fr)] gap-2 p-2 min-h-0 overflow-hidden">
        <div className="grid grid-rows-[minmax(140px,0.9fr)_minmax(180px,1.1fr)] lg:grid-rows-[1.618fr_1fr] gap-2 min-h-0 order-2 lg:order-1">
          <VideoPanel
            ref={videoRef}
            enabled
            variant="dark"
            micActive={isRecording}
            voiceStatus={voiceStatus}
            onFaceAnalysis={handleFaceAnalysis}
          />
          <InterviewRoomChat room={room} />
        </div>
        <InterviewRoomOutline room={room} />
      </div>
    </div>
  );
}
