"use client";

import { useEffect, useRef } from "react";
import { AVATAR_ASSETS } from "./talkingheadAssets";
import { safeMood } from "./talkingheadMood";
import type { HeadInstance } from "./talkingheadTypes";

/** The boot phase callback has the same name as the onProgress/onReady/onFailed contract of AvatarRendererProps. */
interface TalkingHeadBootCallbacks {
  onProgress?: (pct: number) => void;
  onReady?: () => void;
  onFailed?: (err: unknown) => void;
}

/**
 * 3D avatar boot/teardown: dynamic import + Strict Mode dual mount protection + progress reporting
 * + Lock sight after entering the room. Returns the mounting node and instance handle for gaze/emotion/mouth to reuse.
 * This file remains the only boundary where import @met4citizen/talkinghead is allowed.
 */
export function useTalkingHeadBoot(
  avatarId: string,
  { onProgress, onReady, onFailed }: TalkingHeadBootCallbacks,
) {
  const mountRef = useRef<HTMLDivElement>(null);
  const headRef = useRef<HeadInstance | null>(null);
  const bootGenRef = useRef(0);

  // The upthrow in the ready state is driven by the boot process; after the upthrow fails, the stage switches to the channel.
  useEffect(() => {
    const gen = ++bootGenRef.current;
    let cancelled = false;
    let head: HeadInstance | null = null;
    /** Each boot has an independent mount point to avoid clearing the DOM of the next boot during effect cleaning (Strict Mode dual mounting or avatarId switching) */
    let mount: HTMLDivElement | null = null;

    const boot = async () => {
      const node = mountRef.current;
      if (!node) return;
      try {
        const mod = await import("@met4citizen/talkinghead");
        const TalkingHead = (mod as { TalkingHead: new (n: HTMLElement, o?: object) => HeadInstance })
          .TalkingHead;
        if (cancelled || bootGenRef.current !== gen) return;

        const profile = AVATAR_ASSETS[avatarId] || AVATAR_ASSETS.professional_male!;
        const mood = safeMood(profile.mood);
        mount = document.createElement("div");
        mount.style.cssText = "position:absolute;inset:0;width:100%;height:100%;";
        node.replaceChildren(mount);

        const light = profile.light;
        head = new TalkingHead(mount, {
          ttsEndpoint: "",
          lipsyncModules: [],
          cameraView: "head",
          avatarMood: mood,
          avatarIdleEyeContact: 1,
          avatarSpeakingEyeContact: 1,
          avatarIdleHeadMove: 0.08,
          avatarSpeakingHeadMove: 0.1,
          lightAmbientColor: 0x8899aa,
          lightAmbientIntensity: light?.ambient ?? 1.2,
          lightDirectColor: light?.directColor ?? 0xffe6cc,
          lightDirectIntensity: light?.direct ?? 8,
          modelFPS: 30,
        });
        headRef.current = head;

        const avatarOpts: Record<string, unknown> = {
          url: profile.url,
          body: profile.body,
          avatarMood: mood,
          avatarIdleEyeContact: 1,
          avatarSpeakingEyeContact: 1,
          avatarIdleHeadMove: 0.08,
        };
        if (profile.baseline) avatarOpts.baseline = profile.baseline;

        await head.showAvatar(avatarOpts, (ev: unknown) => {
          const e = ev as { lengthComputable?: boolean; loaded?: number; total?: number };
          if (e?.lengthComputable && e.total && e.total > 0) {
            const raw = Math.round((100 * (e.loaded || 0)) / e.total);
            if (bootGenRef.current === gen) onProgress?.(Math.min(100, Math.max(0, raw)));
          }
        });
        if (cancelled || bootGenRef.current !== gen) {
          try {
            head.stop?.();
          } catch {
            /* noop */
          }
          mount?.remove();
          return;
        }
        // After entering the room, lock your gaze and look towards the camera to offset the idle posture offset of the model.
        try {
          head.setBaselineValue?.("eyesLookDown", 0);
          head.setFixedValue?.("eyesLookDown", 0, 200);
          head.setValue("eyesLookDown", 0, 200);
          head.setValue("eyesLookUp", 0.08, 200);
          head.setValue("headRotateX", 0.1, 300);
          head.lookAtCamera?.(1500);
          head.makeEyeContact?.(3000);
        } catch {
          /* ignore */
        }
        if (bootGenRef.current === gen) onReady?.();
      } catch (err) {
        console.warn("3D avatar channel failed to load", avatarId, err);
        if (!cancelled && bootGenRef.current === gen) onFailed?.(err);
      }
    };

    void boot();
    return () => {
      cancelled = true;
      try {
        head?.stop?.();
      } catch {
        /* noop */
      }
      if (headRef.current === head) headRef.current = null;
      try {
        mount?.remove();
      } catch {
        /* noop */
      }
    };
    // avatarId changes and is rebuilt; the callback passed in by the stage is an inline arrow function, and the reference is unstable, so no dependencies are added.
    // (Only the stable setState is called inside the callback, the old closure is still correct)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [avatarId]);

  return { mountRef, headRef };
}
