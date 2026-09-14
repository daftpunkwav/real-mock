"use client";

import type { ComponentType } from "react";

/**
 * Implementation-independent contract for avatar rendering channels.
 *
 * Pages and room components depend only on this contract and AvatarStage.
 * Concrete renderers live behind adapters in renderers/, so channels can be
 * replaced without changing their callers.
 */

/** Supported emotion values from the backend turn protocol. */
const AVATAR_EXPRESSIONS = [
  "neutral",
  "smile",
  "serious",
  "curious",
  "encouraging",
  "skeptical",
  "concerned",
  "angry",
  "sad",
  "happy",
] as const;

export type AvatarExpression = (typeof AVATAR_EXPRESSIONS)[number];

/** Fall back safely when the protocol omits or introduces an emotion value. */
export function toAvatarExpression(value: string | undefined): AvatarExpression {
  return (AVATAR_EXPRESSIONS as readonly string[]).includes(value ?? "")
    ? (value as AvatarExpression)
    : "neutral";
}

export interface AvatarRendererProps {
  avatarId: string;
  /** Scene context; each channel decides how to render its environment. */
  sceneId: string;
  emotion: AvatarExpression;
  /** Whether speech animation should drive the mouth and pose. */
  speaking: boolean;
  /** Real-time 0-1 audio level used to drive the mouth. */
  audioLevel: number;
  /** Optional resource loading progress from 0 to 100. */
  onProgress?(pct: number): void;
  /** Signal that the loading mask can be hidden. */
  onReady?(): void;
  /** Signal that the stage should fall back to the next renderer. */
  onFailed?(err: unknown): void;
}

type AvatarRendererComponent = ComponentType<AvatarRendererProps>;

export interface AvatarRendererDef {
  /** Capability-based rendering channel identifier. */
  id: string;
  /** Return whether the runtime supports this channel; SSR should return false. */
  isSupported(): boolean;
  Component: AvatarRendererComponent;
  /** Optionally prefetch avatar resources before entering the room. */
  prefetch?(avatarId: string): void;
}
