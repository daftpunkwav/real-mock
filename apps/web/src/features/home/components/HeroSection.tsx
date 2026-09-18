"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import { useT } from "@/i18n";
import { SceneRing } from "./SceneRing";
import { StageButton } from "./StageButton";

/** Choreography easing — leads the eye, then settles; matches Vertex's EXPO. */
const introEase = [0.16, 1, 0.3, 1] as const;

function intro(delay: number, y = 10) {
  return {
    initial: { opacity: 0, y },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.7, delay, ease: introEase },
  };
}

export function HeroSection() {
  const reduce = useReducedMotion();
  const t = useT("home");

  return (
    <section className="relative overflow-hidden">
      {/* Faint bank of light along the foot that dissolves back to transparent
          before the section edge — a hard stop here reads as a divider line. */}
      <div
        className="pointer-events-none absolute inset-0"
        aria-hidden
        style={{
          background:
            "linear-gradient(180deg, transparent 55%, color-mix(in srgb, var(--primary) 5%, transparent) 80%, transparent 100%)",
        }}
      />

      <div className="relative mx-auto max-w-[1200px] px-5 sm:px-6 lg:px-8">
        {/* Copy block — centred like a marquee, context first then message */}
        <div className="flex flex-col items-center pt-16 text-center sm:pt-24">
          <motion.h1
            {...(reduce ? {} : intro(0.14, 14))}
            className="text-[clamp(2.1rem,5vw,3.4rem)] font-bold leading-[1.06] tracking-[-0.025em] text-ink"
          >
            {t("hero.title.line1")}{" "}
            <span className="bg-gradient-to-r from-[var(--primary)] to-[#7aabff] bg-clip-text text-transparent">
              {t("hero.title.line2")}
            </span>
          </motion.h1>

          <motion.p
            {...(reduce ? {} : intro(0.24, 9))}
            className="mt-5 max-w-[54ch] text-[14px] leading-[1.7] text-ink-muted [text-wrap:balance] sm:text-[15px]"
          >
            {t("hero.sub1")} {t("hero.sub2")}
          </motion.p>

          <motion.div
            {...(reduce ? {} : intro(0.32, 8))}
            className="mt-8 flex flex-wrap items-center justify-center gap-2.5"
          >
            <StageButton href="/interview">{t("hero.cta.interview")}</StageButton>
            <Link
              href="/resume"
              className="btn-secondary !h-[52px] !px-7 !text-[16px]"
            >
              {t("hero.cta.resume")}
            </Link>
          </motion.div>
        </div>

        {/* Scene zone: the 3D wheel alone, standing on a faint pool of light */}
        <div className="relative mt-2 h-[320px] sm:h-[400px]">
          <motion.div
            {...(reduce ? {} : intro(0.4, 16))}
            className="absolute inset-0"
          >
            <SceneRing />
          </motion.div>
          {/* Pool of light under the wheel. Its centre sits INSIDE the box so
              the falloff reaches zero before every edge — a gradient clipped
              by the box edge reads as a divider line. */}
          <div
            className="pointer-events-none absolute inset-x-0 bottom-0 h-40"
            aria-hidden
            style={{
              background:
                "radial-gradient(46% 62% at 50% 42%, color-mix(in srgb, var(--primary) 11%, transparent), transparent 68%)",
            }}
          />
        </div>
      </div>
    </section>
  );
}
