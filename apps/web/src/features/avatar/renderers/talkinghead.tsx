"use client";

import type { AvatarExpression, AvatarRendererDef, AvatarRendererProps } from "../contract";
import { AVATAR_ASSETS } from "./talkingheadAssets";
import { useTalkingHeadBoot } from "./talkingheadBoot";
import { useTalkingHeadEmotion } from "./talkingheadEmotion";
import { useTalkingHeadGaze } from "./talkingheadGaze";
import { useTalkingHeadMouth } from "./talkingheadMouth";
import { webglSupported } from "./talkingheadSupport";

/**
 * Assembly layer for the @met4citizen/talkinghead 3D avatar adapter.
 *
 * Boot and teardown, gaze, expression morphing, and mouth animation live in
 * dedicated modules. This file only assembles those hooks, mounts the renderer,
 * and exposes metadata; talkingheadBoot owns the dynamic library import.
 */

function TalkingHeadRenderer({
  avatarId,
  emotion,
  speaking,
  audioLevel,
  onProgress,
  onReady,
  onFailed,
}: AvatarRendererProps) {
  const { mountRef, headRef } = useTalkingHeadBoot(avatarId, { onProgress, onReady, onFailed });
  useTalkingHeadGaze(headRef, speaking);
  useTalkingHeadEmotion(headRef, emotion);
  useTalkingHeadMouth(headRef, audioLevel, speaking);

  return <div ref={mountRef} className="absolute inset-0" />;
}

export const talkingheadRenderer: AvatarRendererDef = {
  id: "3d-head",
  isSupported: webglSupported,
  Component: TalkingHeadRenderer,
  prefetch(avatarId: string): void {
    if (typeof window === "undefined") return;
    const profile = AVATAR_ASSETS[avatarId] || AVATAR_ASSETS.professional_male;
    if (!profile) return;
    const link = document.createElement("link");
    link.rel = "prefetch";
    link.as = "fetch";
    link.href = profile.url;
    link.crossOrigin = "anonymous";
    document.head.appendChild(link);
  },
};

export type { AvatarExpression };
