"use client";

/**
 * Hero centrepiece: typographic interview-moment cards placed on a true 3D
 * cylinder (camera at the ring centre, like the Vertex wheel). Cards rotate
 * continuously via requestAnimationFrame; the back half is culled by angle and
 * rotation freezes under prefers-reduced-motion.
 */

import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "framer-motion";
import { useT } from "@/i18n";
import { RING_CARDS, type RingCard } from "../content";

/* Design-space geometry (scaled down as a whole on narrow screens):
   R = cylinder radius, STEP = angular step, CULL = back-half cull angle. */
const DESIGN_WIDTH = 1040;
const RADIUS = 620;
const SPEED_DEG_PER_SEC = 1.7;
const CULL_ANGLE = 47;

const CARD_COUNT = RING_CARDS.length * 2;
const STEP = 360 / CARD_COUNT;

const VARIANT_STYLE: Record<string, string> = {
  role: "linear-gradient(160deg, #1c3a66, #10233f 62%, #0b1a30)",
  probe: "linear-gradient(160deg, #3c1f4e, #241233 62%, #170c22)",
  basics: "linear-gradient(160deg, #123c3c, #0a2424 62%, #071a1a)",
  score: "linear-gradient(160deg, #14492f, #0c2f1f 62%, #082115)",
  system: "linear-gradient(160deg, #1a2f3e, #0e1b26 62%, #09141c)",
  project: "linear-gradient(160deg, #4a3212, #2a1e0a 62%, #1d1406)",
  hr: "linear-gradient(160deg, #4a1f2e, #2a1119 62%, #1d0b12)",
  round: "linear-gradient(160deg, #232a5c, #12162f 62%, #0c0f22)",
  reverse: "linear-gradient(160deg, #2e3440, #1a1e26 62%, #12151b)",
  report: "linear-gradient(160deg, #3e4212, #24260a 62%, #191a06)",
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

export function SceneRing() {
  const t = useT("home");
  const reduce = useReducedMotion();
  const wrapRef = useRef<HTMLDivElement>(null);
  const cardRefs = useRef<(HTMLDivElement | null)[]>([]);
  const phaseRef = useRef(1.5);
  const [scale, setScale] = useState(1);

  // The whole wheel is authored at DESIGN_WIDTH and scaled to the container,
  // so the geometry never reflows mid-rotation.
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      setScale(Math.min(1, el.clientWidth / DESIGN_WIDTH));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const place = (phase: number) => {
      cardRefs.current.forEach((el, i) => {
        if (!el) return;
        const angle = ((((i * STEP + phase) % 360) + 540) % 360) - 180;
        if (Math.abs(angle) > CULL_ANGLE) {
          el.style.visibility = "hidden";
          return;
        }
        el.style.visibility = "visible";
        const rad = (angle * Math.PI) / 180;
        const c = Math.cos(rad);
        el.style.transform = `translate3d(${RADIUS * Math.sin(rad)}px, 0, ${RADIUS * (1 - c)}px) rotateY(${-angle}deg)`;
        el.style.filter = `brightness(${0.55 + 0.5 * c})`;
      });
    };

    if (reduce) {
      place(phaseRef.current);
      return;
    }
    let raf = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const dt = Math.min((now - last) / 1000, 0.1);
      last = now;
      phaseRef.current -= SPEED_DEG_PER_SEC * dt;
      place(phaseRef.current);
      raf = requestAnimationFrame(tick);
    };
    // Reset the timestamp on tab refocus so a backgrounded tab never jumps.
    const onVisibility = () => {
      last = performance.now();
    };
    raf = requestAnimationFrame(tick);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [reduce]);

  return (
    <div ref={wrapRef} className="pointer-events-none relative h-full w-full" aria-hidden>
      <div
        className="absolute left-1/2 top-1/2"
        style={{ transform: `translate(-50%, -50%) scale(${scale})`, width: DESIGN_WIDTH }}
      >
        <div
          className="relative mx-auto"
          style={{
            height: 320,
            perspective: 780,
            perspectiveOrigin: "50% 540px",
            transformStyle: "preserve-3d",
          }}
        >
          {Array.from({ length: CARD_COUNT }, (_, i) => {
            const card = RING_CARDS[i % RING_CARDS.length] as RingCard;
            const accent = VARIANT_ACCENT[card.variant] ?? "#8ab4f8";
            return (
              <div
                key={i}
                ref={(el) => {
                  cardRefs.current[i] = el;
                }}
                className="absolute overflow-hidden rounded-xl border border-white/12 shadow-[0_22px_44px_rgba(0,0,0,0.45)] will-change-transform"
                style={{
                  left: "50%",
                  top: 56,
                  width: 156,
                  height: 216,
                  marginLeft: -78,
                  background: VARIANT_STYLE[card.variant] ?? VARIANT_STYLE.role,
                  backfaceVisibility: "hidden",
                }}
              >
                <div
                  className="absolute inset-0"
                  style={{
                    background:
                      "linear-gradient(180deg, rgba(255,255,255,0.10), rgba(255,255,255,0) 36%)",
                  }}
                />
                <div className="absolute left-3.5 top-3.5 h-1 w-6 rounded-full" style={{ background: accent }} />
                <div className="absolute left-3.5 top-10 right-3.5">
                  <p
                    className="text-[21px] font-bold leading-[1.08] tracking-tight text-white"
                    style={{ textShadow: "0 2px 10px rgba(0,0,0,0.4)" }}
                  >
                    {t(card.titleKey)}
                  </p>
                </div>
                <div className="absolute bottom-3.5 left-3.5 right-3.5">
                  <p className="text-[11px] leading-snug text-white/70">{t(card.subKey)}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
