"use client";

/**
 * Hero centrepiece: typographic interview-moment cards placed on a true 3D
 * cylinder (camera at the ring centre, like the Vertex wheel). Cards rotate
 * continuously via requestAnimationFrame; the back half fades out over an
 * angular band instead of popping (visibility flips only at zero opacity),
 * and rotation freezes under prefers-reduced-motion.
 */

import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "framer-motion";
import { useT } from "@/i18n";
import { RING_CARDS, type RingCard } from "../content";

/* Design-space geometry (scaled down as a whole on narrow screens):
   R = cylinder radius, STEP = angular step. Thirty cards give a continuous
   ring (step 12deg, ~17px gaps at this radius). Cards stay fully opaque up
   to FADE_START degrees, then fade to zero at CULL before being hidden; the
   scale law fits the FULLY-OPAQUE span so solid cards never clip, while
   already-fading cards may run past the container edges and keep the sides
   of the stage full. */
const RADIUS = 860;
const FADE_START = 40;
const CULL_ANGLE = 58;

const CARD_COUNT = RING_CARDS.length * 3;
const STEP = 360 / CARD_COUNT;
const CARD_WIDTH = 164;
const CARD_HEIGHT = 228;
const CARD_TOP = 52;
const VISIBLE_SPAN = 2 * RADIUS * Math.sin((FADE_START * Math.PI) / 180) + CARD_WIDTH;
const SPEED_DEG_PER_SEC = 1.7;

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
    default:
      return null;
  }
}

/* Fractal-noise tile shared by every card face — kills the flat "vector
   plastic" look the same way film grain does. */
const NOISE_URI =
  "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")";

export function SceneRing() {
  const t = useT("home");
  const reduce = useReducedMotion();
  const wrapRef = useRef<HTMLDivElement>(null);
  const cardRefs = useRef<(HTMLDivElement | null)[]>([]);
  const shadeRefs = useRef<(HTMLDivElement | null)[]>([]);
  const phaseRef = useRef(1.5);
  const [scale, setScale] = useState(1);

  // The whole wheel is authored at VISIBLE_SPAN and scaled to the container,
  // so the geometry never reflows mid-rotation. Compute once on mount — under
  // frame throttling the observer's first callback can be delayed.
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const update = () => setScale(Math.min(1, el.clientWidth / VISIBLE_SPAN));
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    // Per-frame writes stay compositor-friendly: transform + opacity only.
    // Depth dimming is a black overlay's opacity — a per-frame filter would
    // force a full repaint of every card on every tick.
    const place = (phase: number) => {
      cardRefs.current.forEach((el, i) => {
        if (!el) return;
        const angle = ((((i * STEP + phase) % 360) + 540) % 360) - 180;
        const abs = Math.abs(angle);
        if (abs > CULL_ANGLE) {
          el.style.visibility = "hidden";
          return;
        }
        el.style.visibility = "visible";
        const rad = (angle * Math.PI) / 180;
        const c = Math.cos(rad);
        el.style.transform = `translate3d(${RADIUS * Math.sin(rad)}px, 0, ${RADIUS * (1 - c)}px) rotateY(${-angle}deg)`;
        el.style.opacity =
          abs <= FADE_START ? "1" : String(Math.max(0, 1 - (abs - FADE_START) / (CULL_ANGLE - FADE_START)));
        const shade = shadeRefs.current[i];
        if (shade) shade.style.opacity = String(0.32 * (1 - c));
      });
    };

    if (reduce) {
      place(phaseRef.current);
      return;
    }
    let raf = 0;
    let last = 0;
    let running = false;
    const tick = (now: number) => {
      const dt = Math.min((now - last) / 1000, 0.1);
      last = now;
      phaseRef.current -= SPEED_DEG_PER_SEC * dt;
      place(phaseRef.current);
      raf = requestAnimationFrame(tick);
    };
    const start = () => {
      if (running) return;
      running = true;
      last = performance.now();
      raf = requestAnimationFrame(tick);
    };
    const stop = () => {
      running = false;
      cancelAnimationFrame(raf);
    };
    // The loop runs only while the wheel is on screen; tab-hidden frames are
    // already throttled by the browser, and a backgrounded wheel costs zero.
    const io = new IntersectionObserver(
      (entries) => (entries[0]?.isIntersecting ? start() : stop()),
      { threshold: 0 },
    );
    if (wrapRef.current) io.observe(wrapRef.current);
    // Reset the timestamp on tab refocus so a backgrounded tab never jumps.
    const onVisibility = () => {
      last = performance.now();
    };
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      stop();
      io.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [reduce]);

  return (
    <div ref={wrapRef} className="pointer-events-none relative h-full w-full" aria-hidden>
      <div
        className="absolute left-1/2 top-1/2"
        style={{ transform: `translate(-50%, -50%) scale(${scale})`, width: VISIBLE_SPAN }}
      >
        <div
          className="relative mx-auto"
          style={{
            height: 320,
            perspective: RADIUS,
            perspectiveOrigin: "50% 540px",
            transformStyle: "preserve-3d",
          }}
        >
          {Array.from({ length: CARD_COUNT }, (_, i) => {
            const card = RING_CARDS[i % RING_CARDS.length] as RingCard;
            const accent = VARIANT_ACCENT[card.variant] ?? "#8ab4f8";
            const isScore = card.variant === "score";
            return (
              <div
                key={i}
                ref={(el) => {
                  cardRefs.current[i] = el;
                }}
                className="absolute overflow-hidden will-change-transform"
                style={{
                  left: "50%",
                  top: CARD_TOP,
                  width: CARD_WIDTH,
                  height: CARD_HEIGHT,
                  marginLeft: -CARD_WIDTH / 2,
                  borderRadius: 14,
                  background: VARIANT_STYLE[card.variant] ?? VARIANT_STYLE.role,
                  backfaceVisibility: "hidden",
                  boxShadow:
                    "0 24px 48px -12px rgba(0,0,0,0.6), 0 4px 12px rgba(0,0,0,0.4)",
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
                <div className={`absolute left-4 right-4 ${isScore ? "top-[84px]" : "top-10"}`}>
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
                <div className={`absolute left-4 right-4 ${isScore ? "top-[148px]" : "top-[116px]"}`}>
                  {cardGraphic(card.variant, accent)}
                </div>

                {/* footer: hairline + caption */}
                <div className="absolute bottom-3.5 left-4 right-4">
                  <div className="mb-2 h-px bg-white/12" />
                  <p className="text-[11px] leading-snug text-white/65">{t(card.subKey)}</p>
                </div>

                {/* skylight hotspot, film grain, then glare + edge light */}
                <div
                  className="absolute inset-0"
                  style={{
                    background:
                      "radial-gradient(120% 58% at 50% -10%, rgba(255,255,255,0.15), transparent 54%)",
                  }}
                />
                <div
                  className="absolute inset-0 opacity-15 mix-blend-overlay"
                  style={{ backgroundImage: NOISE_URI, backgroundSize: "120px 120px" }}
                />
                {/* depth shading, driven per-frame via opacity (never a filter) */}
                <div
                  ref={(el) => {
                    shadeRefs.current[i] = el;
                  }}
                  className="absolute inset-0 bg-black"
                  style={{ opacity: 0, willChange: "opacity" }}
                />
                <div
                  className="absolute inset-0"
                  style={{
                    background:
                      "linear-gradient(155deg, rgba(255,255,255,0.09), rgba(255,255,255,0.02) 40%, transparent 62%)",
                  }}
                />
                <div
                  className="absolute inset-0 rounded-[14px]"
                  style={{
                    boxShadow:
                      "inset 0 0 0 1px rgba(255,255,255,0.12), inset 0 -20px 32px rgba(0,0,0,0.30), inset 0 1px 0 rgba(255,255,255,0.16)",
                  }}
                />
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
