"use client";

/**
 * Hero centrepiece: a perspective ring of per-frame billboarded cards. One
 * rAF loop places each
 * card per frame with translate3d onto a cylinder (camera just outside the
 * near surface) and rotateY(-a) so the card faces the camera, then culls it
 * with visibility past CULL_ANGLE — the card reads as upright at every angle:
 * the slanted sides are perspective, not rotation. Cards carry
 * will-change:transform so Chromium rasterizes each once and reuses that
 * texture while only the transform moves; without the hint the drifting
 * projected scale makes it re-raster periodically and the new tiles land a
 * frame apart (visible as half-card pops). Visibility writes are diffed so
 * culled cards cost nothing; a visible card costs one transform write.
 */

import { useEffect, useRef } from "react";
import { useT } from "@/i18n";
import { RING_CARDS, type RingCard } from "../content";

/* Design-space geometry (scaled as a whole to the container width):
   R = cylinder radius, STEP = angular step, PERSPECTIVE = eye distance.
   Thirty-six cards (18 creatives x2) give a continuous ring (step 10deg).
   The eye sits near the ring centre (P/R = 1.6);
   projected span and mask fade are derived from the projection at CULL_ANGLE
   so the fade hugs the outermost visible cards. */
const RADIUS = 1140;
const PERSPECTIVE = RADIUS * 1.6;

const CARD_COUNT = RING_CARDS.length * 2;
const STEP = 360 / CARD_COUNT;
const CARD_WIDTH = 180;
const CARD_HEIGHT = 240;
const CARD_TOP = 48;
const CULL_ANGLE = 50; // deep inside the mask's zero zone, so culling never shows
const SPEED = 1.7; // deg/s, cards travel left to right: enter at the left rim, exit right
const SCALE_FLOOR = 0.8;

const CULL_RAD = (CULL_ANGLE * Math.PI) / 180;
const S_CULL = PERSPECTIVE / (PERSPECTIVE - RADIUS * (1 - Math.cos(CULL_RAD)));
const VISIBLE_SPAN = 2 * (RADIUS * Math.sin(CULL_RAD) + CARD_WIDTH / 2) * S_CULL;

/* Signed angle of card i for a given phase, wrapped to -180..180, plus the
   transform that puts it on the cylinder facing the camera. */
function angleOf(i: number, phase: number) {
  let a = (i * STEP + phase) % 360;
  if (a > 180) a -= 360;
  if (a < -180) a += 360;
  return a;
}

function transformAt(angleDeg: number) {
  const a = angleDeg * (Math.PI / 180);
  const x = RADIUS * Math.sin(a);
  const z = RADIUS * (1 - Math.cos(a));
  return `translate3d(${x.toFixed(2)}px, 0, ${z.toFixed(2)}px) rotateY(${(-angleDeg).toFixed(3)}deg)`;
}

const VARIANT_STYLE: Record<string, string> = {
  role: "linear-gradient(165deg, #26497c, #16304f 55%, #0b1a30)",
  probe: "linear-gradient(165deg, #4a2760, #2c1540 55%, #180b24)",
  basics: "linear-gradient(165deg, #174a49, #0d2e2e 55%, #081d1d)",
  score: "linear-gradient(165deg, #185637, #0e3825 55%, #082417)",
  system: "linear-gradient(165deg, #1e3849, #101f2c 55%, #0a151e)",
  project: "linear-gradient(165deg, #573a15, #32230c 55%, #221705)",
  hr: "linear-gradient(165deg, #552336, #321320 55%, #220c13)",
  round: "linear-gradient(165deg, #282f66, #151a35 55%, #0d1024)",
  reverse: "linear-gradient(165deg, #343b49, #1d222c 55%, #131720)",
  report: "linear-gradient(165deg, #484d14, #2a2d0a 55%, #1c1e06)",
  intro: "linear-gradient(165deg, #1e3a52, #10243a 55%, #0a1828)",
  coding: "linear-gradient(165deg, #14402c, #0b2a1d 55%, #071d13)",
  tricky: "linear-gradient(165deg, #452413, #2a160b 55%, #1c0e07)",
  pause: "linear-gradient(165deg, #2b313e, #191d27 55%, #10131b)",
  salary: "linear-gradient(165deg, #413012, #2a1e0a 55%, #1c1406)",
  cross: "linear-gradient(165deg, #1c2650, #101735 55%, #0a0f24)",
  english: "linear-gradient(165deg, #3a1f42, #241230 55%, #170b20)",
  offer: "linear-gradient(165deg, #0f4038, #082a24 55%, #051c18)",
};

const VARIANT_ACCENT: Record<string, string> = {
  role: "#8ab4f8",
  probe: "#d0a8ff",
  basics: "#6fd4c4",
  score: "#6fcf97",
  system: "#7fd4f0",
  project: "#ffd66b",
  hr: "#ff9aa8",
  round: "#a8b4ff",
  reverse: "#c5cdd9",
  report: "#d4e08a",
  intro: "#7cd8e0",
  coding: "#8ce8b0",
  tricky: "#ffa870",
  pause: "#cdd8ea",
  salary: "#f5d565",
  cross: "#a3b4f8",
  english: "#e0baf0",
  offer: "#f2d070",
};

/* One quiet CSS motif per variant, painted in the card's lower half so the
   face reads like a magazine cover instead of a flat gradient block. */
function variantMotif(variant: string, accent: string): React.CSSProperties {
  const a = `${accent}2e`;
  const fade = "linear-gradient(180deg, transparent, black 45%)";
  const base = { opacity: 0.55, maskImage: fade, WebkitMaskImage: fade } as const;
  switch (variant) {
    case "role":
      return {
        ...base,
        opacity: 0.4,
        background: `repeating-radial-gradient(circle at 76% 118%, ${a} 0 1px, transparent 1px 13px)`,
      };
    case "probe":
      return {
        ...base,
        background: `repeating-linear-gradient(135deg, ${a} 0 1px, transparent 1px 9px)`,
      };
    case "basics":
      return {
        ...base,
        background: `radial-gradient(${a} 1px, transparent 1.4px)`,
        backgroundSize: "11px 11px",
      };
    case "system":
      return {
        ...base,
        background: `repeating-linear-gradient(180deg, ${a} 0 1px, transparent 1px 15px)`,
      };
    case "project":
      return {
        ...base,
        opacity: 0.7,
        left: 18,
        right: "auto",
        width: 56,
        background: `repeating-linear-gradient(90deg, ${a} 0 2px, transparent 2px 5px, ${a} 5px 3px, transparent 3px 11px)`,
      };
    case "hr":
      return {
        ...base,
        opacity: 0.45,
        background: `linear-gradient(115deg, transparent 32%, ${a} 50%, transparent 68%)`,
      };
    case "round":
      return {
        opacity: 0.8,
        top: "38%",
        bottom: 26,
        left: 14,
        right: 14,
        borderRadius: 8,
        border: `1px solid ${accent}3c`,
      };
    case "reverse":
      return {
        ...base,
        background: `radial-gradient(circle at 26% 50%, ${a} 0 3px, transparent 4px), radial-gradient(circle at 52% 50%, ${a} 0 3px, transparent 4px), radial-gradient(circle at 78% 50%, ${a} 0 3px, transparent 4px)`,
      };
    case "report":
      return {
        ...base,
        opacity: 0.4,
        background: `repeating-linear-gradient(0deg, ${a} 0 1px, transparent 1px 12px), repeating-linear-gradient(90deg, ${a} 0 1px, transparent 1px 12px)`,
      };
    case "intro":
      // Sound arcs radiating from a low corner: an opening voice.
      return {
        ...base,
        opacity: 0.4,
        background: `repeating-radial-gradient(circle at 8% 120%, ${a} 0 1px, transparent 1px 12px)`,
      };
    case "coding":
      // Faint diagonal hatching, like an IDE gutter pattern.
      return {
        ...base,
        opacity: 0.4,
        background: `repeating-linear-gradient(60deg, ${a} 0 1px, transparent 1px 10px)`,
      };
    case "tricky":
      // Hazard stripes: an incident under way.
      return {
        ...base,
        opacity: 0.4,
        background: `repeating-linear-gradient(45deg, ${a} 0 1px, transparent 1px 7px)`,
      };
    case "pause":
      // Sparse wide dots: air, not signal.
      return {
        ...base,
        opacity: 0.35,
        background: `radial-gradient(${a} 1px, transparent 1.4px)`,
        backgroundSize: "15px 15px",
      };
    case "salary":
      // Vertical ticks, like a rising quote ladder.
      return {
        ...base,
        opacity: 0.4,
        background: `repeating-linear-gradient(90deg, ${a} 0 1px, transparent 1px 12px)`,
      };
    case "cross":
      // One soft diagonal beam linking the halves.
      return {
        ...base,
        opacity: 0.4,
        background: `linear-gradient(65deg, transparent 38%, ${a} 50%, transparent 62%)`,
      };
    case "english":
      // Concentric rings from below: words travelling outward.
      return {
        ...base,
        opacity: 0.4,
        background: `repeating-radial-gradient(circle at 50% 135%, ${a} 0 1px, transparent 1px 12px)`,
      };
    case "offer":
      // Scattered bright specks: a quiet confetti.
      return {
        ...base,
        opacity: 0.5,
        background: `radial-gradient(circle at 20% 30%, ${a} 0 2px, transparent 3px), radial-gradient(circle at 70% 20%, ${a} 0 2px, transparent 3px), radial-gradient(circle at 45% 60%, ${a} 0 2px, transparent 3px)`,
      };
    default:
      return { display: "none" };
  }
}

/* A small data-graphic per variant, sitting between the headline and the
   caption — the card face should carry a piece of evidence, not empty air. */
function cardGraphic(variant: string, accent: string): React.ReactNode {
  const dim = `${accent}40`;
  const glow = `${accent}26`;
  switch (variant) {
    case "role":
      // Spec lines: one wide, two shorter — a role card being filled in.
      return (
        <div className="space-y-2">
          <div className="h-1.5 w-4/5 rounded-full" style={{ background: `${accent}66` }} />
          <div className="h-1.5 w-3/5 rounded-full" style={{ background: dim }} />
          <div className="h-1.5 w-2/3 rounded-full" style={{ background: glow }} />
        </div>
      );
    case "probe":
      // Follow-up chain: question line pointing at a narrower follow-up.
      return (
        <div className="space-y-2.5">
          <div className="flex items-center gap-1.5">
            <span className="h-1.5 flex-1 rounded-full" style={{ background: dim }} />
            <span className="h-1.5 w-1.5 rotate-45 border-r border-t" style={{ borderColor: accent }} />
          </div>
          <div className="ml-4 flex items-center gap-1.5">
            <span className="h-1.5 flex-1 rounded-full" style={{ background: glow }} />
            <span className="h-1.5 w-1.5 rotate-45 border-r border-t" style={{ borderColor: dim }} />
          </div>
        </div>
      );
    case "basics":
      // B+ tree: one root edge splitting into three leaves.
      return (
        <div className="pt-1">
          <div className="mx-auto h-px w-3/5" style={{ background: dim }} />
          <div className="mx-auto h-3 w-px" style={{ background: dim }} />
          <div className="mx-auto h-px w-4/5" style={{ background: glow }} />
          <div className="mt-0 flex justify-between px-1">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-3 w-px" style={{ background: i === 1 ? accent : dim }} />
            ))}
          </div>
        </div>
      );
    case "score":
      // Segmented score bar: 3.5 of 5.
      return (
        <div className="flex gap-1">
          {[0, 1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="h-1.5 flex-1 rounded-full"
              style={{
                background: i < 3 ? accent : dim,
                opacity: i === 3 ? 0.55 : i > 3 ? 0.35 : 1,
              }}
            />
          ))}
        </div>
      );
    case "system":
      // Module grid: four services, one highlighted.
      return (
        <div className="grid grid-cols-2 gap-1.5">
          {[0, 1, 2, 3].map((i) => (
            <div
              key={i}
              className="h-5 rounded-[4px]"
              style={{
                border: `1px solid ${i === 2 ? accent : dim}`,
                background: i === 2 ? `${accent}30` : "transparent",
              }}
            />
          ))}
        </div>
      );
    case "project":
      // Code lines: three indented runs of increasing depth.
      return (
        <div className="space-y-2">
          <div className="h-1 w-3/4 rounded-full" style={{ background: dim }} />
          <div className="ml-3 h-1 w-4/5 rounded-full" style={{ background: accent }} />
          <div className="ml-3 h-1 w-1/2 rounded-full" style={{ background: glow }} />
        </div>
      );
    case "hr":
      // Timeline: three checkpoints, the first passed.
      return (
        <div className="relative pl-4">
          <div className="absolute bottom-1 left-[3px] top-1 w-px" style={{ background: dim }} />
          <div className="space-y-2.5">
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="absolute h-2 w-2 rounded-full"
                style={{
                  left: 0,
                  top: i * 14,
                  background: i === 0 ? accent : "transparent",
                  border: `1px solid ${i === 0 ? accent : dim}`,
                }}
              />
            ))}
          </div>
          <div className="space-y-[9px] pt-0.5">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-1 w-2/3 rounded-full" style={{ background: i === 0 ? `${accent}55` : glow }} />
            ))}
          </div>
        </div>
      );
    case "round":
      // Round progress: 4th of 5.
      return (
        <div className="flex items-center gap-1.5">
          {[0, 1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="h-2 w-2 rounded-full"
              style={{
                background: i < 4 ? accent : "transparent",
                opacity: i === 3 ? 1 : 0.45,
                border: i < 4 ? "none" : `1px solid ${dim}`,
              }}
            />
          ))}
          <div className="ml-1 h-1 flex-1 rounded-full" style={{ background: glow }} />
        </div>
      );
    case "reverse":
      // Speech bubble waiting for your question.
      return (
        <div>
          <div
            className="flex h-9 items-center rounded-lg px-2.5"
            style={{ border: `1px solid ${dim}` }}
          >
            <div className="h-1 w-3/5 rounded-full" style={{ background: glow }} />
          </div>
          <div
            className="ml-3 h-2 w-2 -translate-y-1 rotate-45"
            style={{ background: VARIANT_STYLE[variant], borderRight: `1px solid ${dim}`, borderBottom: `1px solid ${dim}` }}
          />
        </div>
      );
    case "report":
      // Miniature bar chart of round scores.
      return (
        <div className="flex h-11 items-end gap-1.5">
          {[10, 16, 22, 30].map((h, i) => (
            <div
              key={i}
              className="w-4 rounded-t-[3px]"
              style={{ height: h, background: i === 3 ? accent : `${accent}45` }}
            />
          ))}
          <div className="ml-1 h-px flex-1 self-end" style={{ background: glow }} />
        </div>
      );
    case "intro":
      // Opening pitch: a speaking dot leading three draft lines.
      return (
        <div className="space-y-2">
          <div className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ background: accent }} />
            <span className="h-1.5 w-3/5 rounded-full" style={{ background: `${accent}66` }} />
          </div>
          <div className="ml-3.5 h-1.5 w-4/5 rounded-full" style={{ background: dim }} />
          <div className="ml-3.5 h-1.5 w-1/2 rounded-full" style={{ background: glow }} />
        </div>
      );
    case "coding":
      // Editor panel: indented code lines and a block cursor.
      return (
        <div className="rounded-lg px-2.5 py-2" style={{ border: `1px solid ${dim}` }}>
          <div className="space-y-1.5">
            <div className="h-1 w-3/5 rounded-full" style={{ background: dim }} />
            <div className="ml-2 h-1 w-4/5 rounded-full" style={{ background: accent }} />
            <div className="ml-2 flex items-center gap-1">
              <div className="h-1 w-1/3 rounded-full" style={{ background: glow }} />
              <div className="h-2.5 w-1" style={{ background: accent }} />
            </div>
          </div>
        </div>
      );
    case "tricky":
      // Incident log: four rows, the failing one lit.
      return (
        <div className="space-y-2">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="flex items-center gap-1.5">
              <span
                className="h-1 w-1 rounded-full"
                style={{ background: i === 2 ? accent : dim }}
              />
              <span
                className="h-1 flex-1 rounded-full"
                style={{
                  background: i === 2 ? accent : i < 2 ? dim : glow,
                  opacity: i === 2 ? 1 : 0.7,
                }}
              />
            </div>
          ))}
        </div>
      );
    case "pause":
      // Waveform with a hole in the middle: the silence itself.
      return (
        <div className="flex h-8 items-center gap-1">
          {[3, 5, 8, 6].map((h, i) => (
            <div key={i} className="w-1 rounded-full" style={{ height: h, background: dim }} />
          ))}
          <div className="flex-1" />
          {[6, 8, 4].map((h, i) => (
            <div key={i} className="w-1 rounded-full" style={{ height: h, background: i === 1 ? accent : dim }} />
          ))}
        </div>
      );
    case "salary":
      // Two offers converging on one number.
      return (
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1">
            <div className="h-1.5 w-8 rounded-full" style={{ background: dim }} />
            <div className="h-1.5 w-1.5 rotate-45 border-l border-t" style={{ borderColor: accent }} />
          </div>
          <div className="h-1 w-6 rounded-full" style={{ background: glow }} />
          <div className="flex items-center gap-1">
            <div className="h-1.5 w-1.5 rotate-45 border-r border-b" style={{ borderColor: accent }} />
            <div className="h-1.5 w-8 rounded-full" style={{ background: dim }} />
          </div>
        </div>
      );
    case "cross":
      // Round 1 node riding a dashed link into round 2.
      return (
        <div className="flex items-center">
          <div className="h-2.5 w-2.5 rounded-full" style={{ border: `1px solid ${dim}` }} />
          <div
            className="h-px flex-1"
            style={{ background: `repeating-linear-gradient(90deg, ${dim} 0 4px, transparent 4px 8px)` }}
          />
          <div className="h-2.5 w-2.5 rounded-full" style={{ background: accent }} />
          <div className="ml-1.5 h-1 w-1/3 rounded-full" style={{ background: glow }} />
        </div>
      );
    case "english":
      // Two bubbles trading turns: one listening, one speaking.
      return (
        <div className="space-y-2">
          <div className="flex h-6 w-4/5 items-center gap-1 rounded-md px-2" style={{ border: `1px solid ${dim}` }}>
            <span className="h-1 w-1 rounded-full" style={{ background: dim }} />
            <span className="h-1 w-1 rounded-full" style={{ background: dim }} />
            <span className="h-1 w-1 rounded-full" style={{ background: dim }} />
          </div>
          <div
            className="ml-5 flex h-6 w-3/5 items-center gap-1 rounded-md px-2"
            style={{ border: `1px solid ${accent}66`, background: `${accent}14` }}
          >
            <span className="h-1 w-1 rounded-full" style={{ background: accent }} />
            <span className="h-1 flex-1 rounded-full" style={{ background: glow }} />
          </div>
        </div>
      );
    case "offer":
      // Check ring beside two settled lines.
      return (
        <div className="flex items-center gap-2.5">
          <div
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full"
            style={{ border: `1px solid ${accent}88` }}
          >
            <div className="h-2.5 w-1.5 -translate-y-px rotate-45 border-b-2 border-r-2" style={{ borderColor: accent }} />
          </div>
          <div className="flex-1 space-y-1.5">
            <div className="h-1.5 w-4/5 rounded-full" style={{ background: `${accent}66` }} />
            <div className="h-1.5 w-3/5 rounded-full" style={{ background: glow }} />
          </div>
        </div>
      );
    default:
      return null;
  }
}

export function SceneRing() {
  const t = useT("home");
  const wrapRef = useRef<HTMLDivElement>(null);
  const scaleRef = useRef<HTMLDivElement>(null);
  const ringRef = useRef<HTMLDivElement>(null);

  // The wheel is authored at VISIBLE_SPAN and scaled to the container width
  // in BOTH directions, so the band always spans the scene edge to edge (no
  // dead margins on wide screens). Applied straight to the wrapper's style:
  // resizes must never re-render the cards, whose inline transforms belong to
  // the rAF loop.
  useEffect(() => {
    const el = wrapRef.current;
    const scaled = scaleRef.current;
    if (!el || !scaled) return;
    const update = () => {
      const s = Math.max(SCALE_FLOOR, el.clientWidth / VISIBLE_SPAN);
      scaled.style.transform = `translate(-50%, -50%) scale(${s})`;
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // The placement loop. dt is clamped and re-based on visibilitychange so a
  // backgrounded tab does not fast-forward the wheel on return. Off-screen,
  // the loop parks entirely (the IO gate) instead of burning rAF.
  useEffect(() => {
    const ring = ringRef.current;
    if (!ring) return;
    const cards = Array.from(ring.children) as HTMLElement[];
    const culled = new Array<boolean>(cards.length).fill(true);
    let phase = 0;
    let raf = 0;
    let last = 0;
    let onScreen = true;

    const render = () => {
      for (let i = 0; i < cards.length; i++) {
        const el = cards[i];
        if (!el) continue;
        const a = angleOf(i, phase);
        const hide = Math.abs(a) > CULL_ANGLE;
        if (hide) {
          if (!culled[i]) {
            el.style.visibility = "hidden";
            culled[i] = true;
          }
          continue;
        }
        if (culled[i]) {
          el.style.visibility = "visible";
          culled[i] = false;
        }
        el.style.transform = transformAt(a);
      }
    };

    const tick = (t: number) => {
      const dt = Math.min((t - last) / 1000, 0.1);
      last = t;
      phase += SPEED * dt;
      if (phase >= 360) phase -= 360;
      render();
      raf = requestAnimationFrame(tick);
    };

    const start = () => {
      last = performance.now();
      raf = requestAnimationFrame(tick);
    };
    const stop = () => {
      if (raf) cancelAnimationFrame(raf);
      raf = 0;
    };

    render();
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const io = new IntersectionObserver(
      (entries) => {
        onScreen = entries[0]?.isIntersecting ?? true;
        if (onScreen && !raf) start();
        if (!onScreen && raf) stop();
      },
      { threshold: 0 },
    );
    io.observe(ring);
    const onVis = () => {
      if (!document.hidden && onScreen && !raf) start();
    };
    document.addEventListener("visibilitychange", onVis);
    if (onScreen) start();
    return () => {
      stop();
      io.disconnect();
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  return (
    <div ref={wrapRef} className="pointer-events-none relative h-full w-full" aria-hidden>
      <div
        ref={scaleRef}
        className="absolute left-1/2 top-1/2"
        style={{ transform: "translate(-50%, -50%)", width: VISIBLE_SPAN }}
      >
        <div
          className="relative mx-auto"
          style={{
            height: 320,
            // Side fade without an opaque cover: a mask on this ancestor
            // composites the already-projected 3D result, so it neither
            // flattens the cylinder nor hides the starfield behind it.
            // black 13%/87% == the projected x of a card at ~36deg, so the
            // fade owns the 36-42deg rim and hits zero right where cards
            // are culled. no-repeat: cards can paint past the box and a
            // repeating tile would fade them back in.
            maskImage:
              "linear-gradient(90deg, transparent 0, black 13%, black 87%, transparent 100%)",
            maskRepeat: "no-repeat",
            WebkitMaskImage:
              "linear-gradient(90deg, transparent 0, black 13%, black 87%, transparent 100%)",
            WebkitMaskRepeat: "no-repeat",
          }}
        >
          {/* Perspective stage: the eye sits near the ring centre; each card
              is placed per frame and billboarded to face it. */}
          <div
            className="absolute inset-0"
            style={{ perspective: PERSPECTIVE, perspectiveOrigin: "50% 540px" }}
          >
            <div ref={ringRef} className="h-full w-full">
              {Array.from({ length: CARD_COUNT }, (_, i) => {
                const card = RING_CARDS[i % RING_CARDS.length] as RingCard;
                const accent = VARIANT_ACCENT[card.variant] ?? "#8ab4f8";
                const isScore = card.variant === "score";
                const a0 = angleOf(i, 0);
                const visible0 = Math.abs(a0) <= CULL_ANGLE;
                return (
                  <div
                    key={i}
                    className="absolute overflow-hidden"
                    style={{
                      left: "50%",
                      top: CARD_TOP,
                      width: CARD_WIDTH,
                      height: CARD_HEIGHT,
                      marginLeft: -CARD_WIDTH / 2,
                      // SSR-safe initial placement at phase 0; the loop
                      // owns these two properties from hydration on.
                      transform: visible0 ? transformAt(a0) : undefined,
                      visibility: visible0 ? "visible" : "hidden",
                      // Pin the raster: see the file header.
                      willChange: "transform",
                      borderRadius: 16,
                      // One pre-composited background stack keeps each card a
                      // single cheap paint: a 1px catch-light along the top
                      // bevel, skylight from above, a diagonal glare, side
                      // shading that reads as cylindrical curvature, bottom
                      // volume grounding the caption, then the variant color.
                      background: [
                        "linear-gradient(180deg, rgba(255,255,255,0.22) 0 1px, transparent 1px)",
                        "radial-gradient(120% 58% at 50% -10%, rgba(255,255,255,0.15), transparent 54%)",
                        "linear-gradient(155deg, rgba(255,255,255,0.09), rgba(255,255,255,0.02) 40%, transparent 62%)",
                        "linear-gradient(90deg, rgba(0,0,0,0.22), transparent 16% 84%, rgba(0,0,0,0.22))",
                        "linear-gradient(180deg, transparent 58%, rgba(0,0,0,0.30))",
                        VARIANT_STYLE[card.variant] ?? VARIANT_STYLE.role,
                      ].join(", "),
                      border: "1px solid rgba(255,255,255,0.13)",
                    }}
                  >
                    {/* quiet variant-specific motif, lower half */}
                    <div className="absolute inset-x-3.5 bottom-0 top-[42%]" style={variantMotif(card.variant, accent)} />

                    {/* kicker: index + hairline */}
                    <div className="absolute left-4 right-4 top-4 flex items-center gap-2">
                      <span
                        className="font-mono text-[10px] font-semibold tracking-[0.14em]"
                        style={{ color: accent }}
                      >
                        {String((i % RING_CARDS.length) + 1).padStart(2, "0")}
                      </span>
                      <span className="h-px flex-1" style={{ background: `${accent}40` }} />
                    </div>

                    {/* headline — the score card gets a giant tabular numeral */}
                    <div className={`absolute left-4 right-4 ${isScore ? "top-[88px]" : "top-11"}`}>
                      <p
                        className={
                          isScore
                            ? "font-mono text-[46px] font-bold leading-none tracking-tight text-white"
                            : "text-[22px] font-bold leading-[1.12] tracking-tight text-white"
                        }
                        style={{ textShadow: "0 2px 12px rgba(0,0,0,0.45)" }}
                      >
                        {t(card.titleKey)}
                      </p>
                    </div>

                    {/* the evidence: a small data-graphic per variant */}
                    <div className={`absolute left-4 right-4 ${isScore ? "top-[156px]" : "top-[120px]"}`}>
                      {cardGraphic(card.variant, accent)}
                    </div>

                    {/* footer: hairline + caption */}
                    <div className="absolute bottom-4 left-4 right-4">
                      <div className="mb-2 h-px bg-white/12" />
                      <p className="text-[11px] leading-snug text-white/65">{t(card.subKey)}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
