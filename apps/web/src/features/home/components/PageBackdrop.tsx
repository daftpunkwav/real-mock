"use client";

import { useMemo } from "react";
import { motion, useReducedMotion, useScroll, useTransform } from "framer-motion";

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
    const y = (rand() * 140).toFixed(2);
    const alpha = (min + rand() * (max - min)).toFixed(2);
    shadows.push(`${x}vw ${y}vh 0 0 rgba(148,163,184,${alpha})`);
  }
  return shadows.join(", ");
}

/**
 * Full-page backdrop shared by every home section — a staged night sky:
 * three star layers (far / mid / near) that drift apart on scroll for
 * parallax depth, three vast nebula washes giving the void a colour floor,
 * a breathing near layer, and the faint brand bank along the foot.
 */
export function PageBackdrop() {
  const reduce = useReducedMotion();
  const faintStars = useMemo(() => starShadowList(150, 20260918, [0.04, 0.2]), []);
  const midStars = useMemo(() => starShadowList(56, 777, [0.12, 0.36]), []);
  const brightStars = useMemo(() => starShadowList(16, 42, [0.42, 0.78]), []);

  // Parallax: the deeper the layer, the more it trails the scroll. Layers
  // start 320px above the viewport so the drift never exposes a bare edge.
  const { scrollY } = useScroll();
  const yFar = useTransform(scrollY, [0, 4000], [0, reduce ? 0 : 70]);
  const yMid = useTransform(scrollY, [0, 4000], [0, reduce ? 0 : 150]);
  const yNear = useTransform(scrollY, [0, 4000], [0, reduce ? 0 : 260]);

  return (
    <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden" aria-hidden>
      {/* nebula washes — barely-there colour pools so the void has depth */}
      <div
        className="absolute inset-0"
        style={{
          background: [
            "radial-gradient(1100px 700px at 12% -8%, color-mix(in srgb, var(--primary) 5%, transparent), transparent 62%)",
            "radial-gradient(900px 620px at 88% 16%, color-mix(in srgb, #7c5cff 4%, transparent), transparent 60%)",
            "radial-gradient(1000px 720px at 52% 110%, color-mix(in srgb, #1fb6c9 3.5%, transparent), transparent 58%)",
          ].join(", "),
        }}
      />

      {/* The night sky belongs to the dark stage; on the light surface the
          grain would read as dirt, so .home-stars fades the layers out. */}
      <div className="home-stars absolute inset-0">
        <motion.div style={{ y: yFar }} className="absolute inset-x-0 -top-80 bottom-0">
          <div
            className="absolute left-0 top-0 h-px w-px rounded-full"
            style={{ boxShadow: faintStars }}
          />
        </motion.div>

        <motion.div style={{ y: yMid }} className="absolute inset-x-0 -top-80 bottom-0">
          <div
            className="absolute left-0 top-0 h-[1.5px] w-[1.5px] rounded-full"
            style={{ boxShadow: midStars }}
          />
        </motion.div>

        <motion.div
          style={{ y: yNear }}
          className="star-breathe absolute inset-x-0 -top-80 bottom-0"
        >
          <div
            className="absolute left-0 top-0 h-[2.5px] w-[2.5px] rounded-full"
            style={{ boxShadow: brightStars }}
          />
        </motion.div>
      </div>

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
