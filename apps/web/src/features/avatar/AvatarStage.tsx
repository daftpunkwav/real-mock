"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2 } from "lucide-react";
import { useT } from "@/i18n";
import { toAvatarExpression, type AvatarRendererDef } from "./contract";
import { talkingheadRenderer } from "./renderers/talkinghead";
import { cssPortraitRenderer } from "./renderers/css-portrait";

/**
 * Single entry point for the interviewer avatar stage.
 *
 * Owns the scene background, capability-based renderer selection with fallback,
 * and the loading mask. Rendering details remain inside renderers/ adapters.
 */

const SCENE_IMG: Record<string, string> = {
  meeting_room: "/scenes/meeting_room.svg",
  glass_office: "/scenes/glass_office.svg",
  online_interview: "/scenes/online_interview.svg",
  boardroom: "/scenes/boardroom.svg",
  startup_loft: "/scenes/startup_loft.svg",
  library_corner: "/scenes/library_corner.svg",
};

const SCENE_FALLBACK: Record<string, string> = {
  meeting_room: "linear-gradient(160deg, #0f172a 0%, #1e3a5f 55%, #0b1220 100%)",
  glass_office: "linear-gradient(160deg, #111827 0%, #1f2937 50%, #0f172a 100%)",
  online_interview: "linear-gradient(160deg, #020617 0%, #1e293b 60%, #0f172a 100%)",
  boardroom: "linear-gradient(160deg, #1c1917 0%, #44403c 50%, #0c0a09 100%)",
  startup_loft: "linear-gradient(160deg, #292524 0%, #57534e 45%, #1c1917 100%)",
  library_corner: "linear-gradient(160deg, #1e1b4b 0%, #312e81 50%, #0f172a 100%)",
};

/** Renderer priority from highest to lowest. */
const RENDERERS: readonly AvatarRendererDef[] = [talkingheadRenderer, cssPortraitRenderer];

function pickRenderer(): AvatarRendererDef {
  for (const r of RENDERERS) {
    try {
      if (r.isSupported()) return r;
    } catch {
      /* Treat capability-detection failures as unsupported. */
    }
  }
  return cssPortraitRenderer;
}

export interface AvatarStageProps {
  avatarId: string;
  sceneId: string;
  /** Turn-protocol emotion; unknown values fall back to neutral. */
  emotion?: string;
  speaking?: boolean;
  audioLevel?: number;
}

export function AvatarStage({
  avatarId,
  sceneId,
  emotion = "neutral",
  speaking = false,
  audioLevel = 0,
}: AvatarStageProps) {
  const primary = useMemo(pickRenderer, []);
  const t = useT("media");
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false);
  const [loadPct, setLoadPct] = useState(0);

  // Reset fallback state when switching avatars so new resources can retry the 3D channel.
  useEffect(() => {
    setFailed(false);
    setReady(false);
    setLoadPct(0);
  }, [avatarId]);

  const active = failed ? cssPortraitRenderer : primary;
  const showLoading = !ready && active.id !== cssPortraitRenderer.id;
  const Renderer = active.Component;

  return (
    <div
      className="relative w-full h-full min-h-[180px] rounded-xl overflow-hidden border border-white/10"
      style={{ background: SCENE_FALLBACK[sceneId] || SCENE_FALLBACK.meeting_room }}
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={SCENE_IMG[sceneId] || SCENE_IMG.meeting_room}
        alt=""
        className="absolute inset-0 w-full h-full object-cover opacity-85 pointer-events-none"
      />
      <Renderer
        key={`${active.id}:${avatarId}`}
        avatarId={avatarId}
        sceneId={sceneId}
        emotion={toAvatarExpression(emotion)}
        speaking={speaking}
        audioLevel={audioLevel}
        onProgress={setLoadPct}
        onReady={() => setReady(true)}
        onFailed={() => setFailed(true)}
      />
      {showLoading && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 bg-black/50 text-white/80 text-xs">
          <Loader2 className="animate-spin text-brand-400" size={22} />
          <span>
            {t("avatar.loading3d")}
            {loadPct > 0 ? ` ${loadPct}%` : ""}
          </span>
          <span className="text-white/40">{t("avatar.loading3dHint")}</span>
        </div>
      )}
      {failed && primary.id !== cssPortraitRenderer.id && (
        <div className="absolute bottom-2 left-2 right-2 z-10 rounded-md bg-black/65 px-2 py-1.5 text-[11px] text-amber-200/95 text-center">
          {t("avatar.stage3dFallback")}
        </div>
      )}
    </div>
  );
}

/** Delegate resource prefetching to each renderer that supports it. */
export function prefetchAvatar(avatarId: string): void {
  for (const r of RENDERERS) {
    try {
      r.prefetch?.(avatarId);
    } catch {
      /* Prefetch failures must not block the room flow. */
    }
  }
}
