"use client";

import { useT } from "@/i18n";
import type { AvatarProfile } from "./avatarProfiles";
import type { InterviewerAvatarMotion } from "./useInterviewerAvatarMotion";

/**
 * Detailed bust of realistic interviewer (SVG portrait layer, purely for display).
 * Only consumes profile color matching and motion performance parameters, excluding scenes/corners and other chrome.
 */

interface InterviewerAvatarPortraitProps {
  profile: AvatarProfile;
  emotion: string;
  speaking: boolean;
  motion: InterviewerAvatarMotion;
}

export function InterviewerAvatarPortrait({
  profile,
  emotion,
  speaking,
  motion: { mouthOpen, blink },
}: InterviewerAvatarPortraitProps) {
  const t = useT("media");
  const browY =
    emotion === "serious" || emotion === "angry"
      ? 3
      : emotion === "curious"
        ? -2
        : emotion === "smile" || emotion === "happy" || emotion === "encouraging"
          ? -1
          : emotion === "concerned" || emotion === "sad"
            ? 1.5
            : 0;
  const eyeSquint =
    emotion === "smile" || emotion === "happy" || emotion === "encouraging" ? 0.85 : 1;
  const mouthBase =
    emotion === "smile" || emotion === "happy"
      ? 0.35
      : emotion === "serious" || emotion === "angry"
        ? 0.04
        : emotion === "encouraging"
          ? 0.25
          : 0.12;
  const mouthH = speaking ? 6 + mouthOpen * 14 : 4 + mouthBase * 8;
  const mouthW = speaking ? 22 + mouthOpen * 6 : 20;
  const cheekOpacity =
    emotion === "smile" || emotion === "happy" || emotion === "encouraging" ? 0.35 : 0.12;

  return (
    <svg
      viewBox="0 0 200 260"
      className="w-full h-full drop-shadow-2xl"
      style={{
        filter: emotion === "serious" ? "saturate(0.85) contrast(1.05)" : undefined,
      }}
      aria-label={t(profile.labelKey)}
    >
      {/* Shoulders/suit */}
      <ellipse cx="100" cy="250" rx="88" ry="48" fill={profile.suit} />
      <path
        d="M40 220 Q100 200 160 220 L170 260 L30 260 Z"
        fill={profile.suit}
      />
      {/* shirt collar */}
      <path d="M78 210 L100 235 L122 210 L115 248 L85 248 Z" fill={profile.shirt} />
      <rect x="96" y="220" width="8" height="30" rx="1" fill={profile.accent} opacity={0.85} />

      {/* neck */}
      <rect x="88" y="145" width="24" height="32" rx="6" fill={profile.skin} />

      {/* Head and shadow */}
      <ellipse cx="100" cy="100" rx="52" ry="58" fill={profile.skin} />
      <ellipse cx="100" cy="108" rx="40" ry="48" fill="#000" opacity={0.06} />

      {/* Hair — multi-layer path overlay */}
      {profile.gender === "female" ? (
        <>
          <ellipse cx="100" cy="72" rx="54" ry="42" fill={profile.hair} />
          <path d="M48 90 Q40 140 55 180 Q70 150 72 100 Z" fill={profile.hair} />
          <path d="M152 90 Q160 140 145 180 Q130 150 128 100 Z" fill={profile.hair} />
          <path d="M55 55 Q100 28 145 55 Q140 85 100 76 Q60 85 55 55 Z" fill={profile.hair} />
          <path d="M70 48 Q100 38 130 48" stroke="#000" strokeWidth="3" opacity={0.12} fill="none" />
        </>
      ) : (
        <>
          <path
            d="M46 98 Q48 42 100 36 Q152 42 154 98 Q148 68 100 64 Q52 68 46 98 Z"
            fill={profile.hair}
          />
          <ellipse cx="100" cy="58" rx="48" ry="26" fill={profile.hair} />
          <path d="M55 70 Q100 52 145 70" stroke="#000" strokeWidth="2" opacity={0.15} fill="none" />
        </>
      )}

      {/* Eyebrow */}
      <path
        d={`M68 ${78 + browY} Q80 ${72 + browY} 90 ${78 + browY}`}
        stroke={profile.hair}
        strokeWidth="2.8"
        fill="none"
        strokeLinecap="round"
      />
      <path
        d={`M110 ${78 + browY} Q120 ${72 + browY} 132 ${78 + browY}`}
        stroke={profile.hair}
        strokeWidth="2.8"
        fill="none"
        strokeLinecap="round"
      />

      {/* Eyes - sclera/iris/highlight three layers */}
      <ellipse cx="80" cy="95" rx="10" ry={7.5 * blink * eyeSquint} fill="#fff" />
      <ellipse cx="120" cy="95" rx="10" ry={7.5 * blink * eyeSquint} fill="#fff" />
      <ellipse cx="80" cy="95" rx="5" ry={5 * blink * eyeSquint} fill="#1e293b" />
      <ellipse cx="120" cy="95" rx="5" ry={5 * blink * eyeSquint} fill="#1e293b" />
      <circle cx="82" cy={93} r={1.8 * blink} fill="#fff" opacity={0.95} />
      <circle cx="122" cy={93} r={1.8 * blink} fill="#fff" opacity={0.95} />
      <path
        d={`M70 ${88 - (1 - blink) * 4} Q80 ${86 - (1 - blink) * 4} 90 ${88 - (1 - blink) * 4}`}
        stroke={profile.hair}
        strokeWidth="1.2"
        fill="none"
        opacity={0.35}
      />
      <path
        d={`M110 ${88 - (1 - blink) * 4} Q120 ${86 - (1 - blink) * 4} 130 ${88 - (1 - blink) * 4}`}
        stroke={profile.hair}
        strokeWidth="1.2"
        fill="none"
        opacity={0.35}
      />

      {/* nose */}
      <path
        d="M100 102 L97 118 Q100 123 103 118 Z"
        fill={profile.skin}
        stroke="#c9956c"
        strokeWidth="0.9"
        opacity={0.75}
      />

      {/* cheek */}
      <ellipse cx="62" cy="115" rx="11" ry="7" fill="#e07a5f" opacity={cheekOpacity} />
      <ellipse cx="138" cy="115" rx="11" ry="7" fill="#e07a5f" opacity={cheekOpacity} />

      {/* Mouth - volume driver */}
      {emotion === "smile" && !speaking ? (
        <path
          d="M84 132 Q100 148 116 132"
          stroke="#b85c48"
          strokeWidth="2.8"
          fill="none"
          strokeLinecap="round"
        />
      ) : (
        <ellipse
          cx="100"
          cy="134"
          rx={mouthW / 2}
          ry={mouthH / 2}
          fill={speaking ? "#4a1f1f" : "#c47868"}
        />
      )}
      {speaking && mouthOpen > 0.35 && (
        <ellipse cx="100" cy="136" rx={mouthW / 3.2} ry={mouthH / 3.5} fill="#d48a8a" opacity={0.55} />
      )}
    </svg>
  );
}
