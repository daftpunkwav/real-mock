"use client";

import { useMemo } from "react";

/** Fixed-seed PRNG so SSR and client render the identical starfield. */
function mulberry32(seed: number) {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function starShadowList(count: number, seed: number, alphaRange: [number, number]) {
  const rand = mulberry32(seed);
  const [min, max] = alphaRange;
  const shadows: string[] = [];
  for (let i = 0; i < count; i++) {
    const x = (rand() * 100).toFixed(2);
    const y = (rand() * 100).toFixed(2);
    const alpha = (min + rand() * (max - min)).toFixed(2);
    shadows.push(`${x}vw ${y}vh 0 0 rgba(148,163,184,${alpha})`);
  }
  return shadows.join(", ");
}

/**
 * Full-page backdrop shared by every home section: a fixed starfield plus a
 * faint brand-colored bank of light at the foot. Fixed positioning keeps the
 * stars anchored while content scrolls over them — one continuous stage.
 */
export function PageBackdrop() {
  const faintStars = useMemo(() => starShadowList(150, 20260918, [0.05, 0.26]), []);
  const brightStars = useMemo(() => starShadowList(18, 42, [0.35, 0.65]), []);

  return (
    <div className="pointer-events-none fixed inset-0 z-0" aria-hidden>
      <div
        className="absolute left-0 top-0 h-px w-px rounded-full"
        style={{ boxShadow: faintStars }}
      />
      <div
        className="absolute left-0 top-0 h-[2px] w-[2px] rounded-full"
        style={{ boxShadow: brightStars, filter: "blur(0.6px)" }}
      />
      <div
        className="absolute inset-x-0 bottom-0 h-[45vh]"
        style={{
          background:
            "linear-gradient(180deg, transparent, color-mix(in srgb, var(--primary) 5%, transparent))",
        }}
      />
    </div>
  );
}
