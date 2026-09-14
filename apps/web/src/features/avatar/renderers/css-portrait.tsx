"use client";

import { useEffect } from "react";
import { InterviewerAvatar } from "../InterviewerAvatar";
import type { AvatarRendererDef, AvatarRendererProps } from "../contract";

/**
 * Flat image rendering pass: CSS/SVG vector portrait (no external resources or WebGL dependencies).
 * It has the same contract and priority as the 3D channel and participates in channel selection. It also serves as a fallback for 3D loading failure.
 */
function CssPortraitRenderer({
  avatarId,
  sceneId,
  emotion,
  speaking,
  audioLevel,
  onReady,
}: AvatarRendererProps) {
  useEffect(() => {
    onReady?.();
  }, [onReady]);

  return (
    <InterviewerAvatar
      avatarId={avatarId}
      sceneId={sceneId}
      emotion={emotion}
      speaking={speaking}
      audioLevel={audioLevel}
    />
  );
}

export const cssPortraitRenderer: AvatarRendererDef = {
  id: "css-portrait",
  isSupported: () => true,
  Component: CssPortraitRenderer,
};
