"use client";

import { useT } from "@/i18n";
import { AVATAR_PROFILES } from "./avatarProfiles";
import { InterviewerAvatarPortrait } from "./InterviewerAvatarPortrait";
import { SCENE_FALLBACK, SCENES } from "./avatarScenes";
import { useInterviewerAvatarMotion } from "./useInterviewerAvatarMotion";

interface InterviewerAvatarProps {
  avatarId: string;
  sceneId: string;
  emotion?: string;
  speaking?: boolean;
  /** 0–1 real-time volume, taking precedence over random embouchure */
  audioLevel?: number;
  onAudioLevel?: (level: number) => void;
}

/**
 * Simulated interviewer portrait: scene layer + bust + speech ripple/corner mark UI.
 * Lip/wink logic is in useInterviewerAvatarMotion, SVG portraits are in
 * InterviewerAvatarPortrait; This component is only assembled with chrome.
 */
export function InterviewerAvatar({
  avatarId,
  sceneId,
  emotion = "neutral",
  speaking = false,
  audioLevel = 0,
}: InterviewerAvatarProps) {
  const t = useT("media");
  const profile = AVATAR_PROFILES[avatarId] || AVATAR_PROFILES.professional_male!;
  const { mouthOpen, blink } = useInterviewerAvatarMotion(speaking, audioLevel);

  const sceneBg = SCENE_FALLBACK[sceneId] || SCENE_FALLBACK.meeting_room;
  const sceneImg = SCENES[sceneId] || SCENES.meeting_room;

  return (
    <div className="relative w-full h-full overflow-hidden rounded-xl" style={{ background: sceneBg }}>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={sceneImg} alt="" className="absolute inset-0 w-full h-full object-cover opacity-90" />
      <div className="absolute inset-0 opacity-15 bg-[url('/scenes/pattern.svg')] bg-cover" />
      {/* soft light */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse 60% 50% at 50% 70%, rgba(255,255,255,0.12) 0%, transparent 70%)",
        }}
      />

      {/* bust area */}
      <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-[min(100%,340px)] h-[88%] flex flex-col items-center justify-end">
        <InterviewerAvatarPortrait
          profile={profile}
          emotion={emotion}
          speaking={speaking}
          motion={{ mouthOpen, blink }}
        />
      </div>

      {/* speaking ripples */}
      {speaking && (
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 flex gap-1 items-end h-6">
          {[0, 1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="w-1 rounded-full bg-white/70 animate-pulse"
              style={{
                height: `${8 + ((i + mouthOpen * 5) % 5) * 4}px`,
                animationDelay: `${i * 80}ms`,
              }}
            />
          ))}
        </div>
      )}

      <div className="absolute top-4 left-4 flex items-center gap-2">
        <span
          className="w-2 h-2 rounded-full"
          style={{ background: speaking ? "#22c55e" : profile.accent }}
        />
        <span className="text-white/90 text-sm font-medium drop-shadow">
          {t(profile.labelKey)}
        </span>
      </div>
      {emotion !== "neutral" && (
        <div className="absolute top-4 right-4 text-xs text-white/70 bg-black/30 px-2 py-0.5 rounded-full">
          {emotion === "smile"
            ? t("avatar.emotionSmile")
            : emotion === "serious"
              ? t("avatar.emotionSerious")
              : emotion}
        </div>
      )}
    </div>
  );
}
