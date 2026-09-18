"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight, Zap } from "lucide-react";
import { useT } from "@/i18n";
import { HeroInterviewPreview } from "./HeroInterviewPreview";
import { SceneRing } from "./SceneRing";

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
      {/* Faint bank of light along the foot — the starfield itself is page-level */}
      <div
        className="pointer-events-none absolute inset-0"
        aria-hidden
        style={{
          background:
            "linear-gradient(180deg, transparent 55%, color-mix(in srgb, var(--primary) 5%, transparent))",
        }}
      />

      <div className="relative mx-auto max-w-[1200px] px-5 sm:px-6 lg:px-8">
        {/* Copy block — centred like a marquee, context first then message */}
        <div className="flex flex-col items-center pt-14 text-center sm:pt-20">
          <motion.div
            {...(reduce ? {} : intro(0.05, 8))}
            className="glass-card inline-flex items-center gap-2.5 rounded-xl px-1.5 py-1.5 pr-4"
          >
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-b from-[var(--primary)] to-[#1a63d8] shadow-sm">
              <Zap size={13} className="text-white" fill="currentColor" />
            </span>
            <span className="text-[12px] font-medium text-ink-muted">{t("hero.badge")}</span>
          </motion.div>

          <motion.h1
            {...(reduce ? {} : intro(0.14, 14))}
            className="mt-6 text-[clamp(2.1rem,5vw,3.4rem)] font-bold leading-[1.06] tracking-[-0.025em] text-ink"
          >
            {t("hero.title.line1")}
            <br />
            <span className="bg-gradient-to-r from-[var(--primary)] to-[#7aabff] bg-clip-text text-transparent">
              {t("hero.title.line2")}
            </span>
          </motion.h1>

          <motion.p
            {...(reduce ? {} : intro(0.24, 9))}
            className="mt-5 max-w-[52ch] text-[14px] leading-[1.7] text-ink-muted sm:text-[15px]"
          >
            {t("hero.sub1")}
            <br className="hidden sm:block" />
            {t("hero.sub2")}
          </motion.p>

          <motion.div
            {...(reduce ? {} : intro(0.32, 8))}
            className="mt-8 flex flex-wrap items-center justify-center gap-2.5"
          >
            <Link href="/interview" className="btn-primary !h-11 !px-6 !text-[15px]">
              {t("hero.cta.interview")}
              <ArrowRight size={15} className="btn-arrow transition-transform" />
            </Link>
            <Link href="/resume" className="btn-secondary !h-11 !px-6 !text-[15px]">
              {t("hero.cta.resume")}
            </Link>
          </motion.div>
        </div>

        {/* Scene zone: the 3D wheel rises behind, the live-interview mock lands
            in FRONT of its lower third — the overlap sells the depth. */}
        <div className="relative mt-1 h-[300px] sm:h-[340px]">
          <motion.div
            {...(reduce ? {} : intro(0.4, 16))}
            className="absolute inset-0"
          >
            <SceneRing />
          </motion.div>
          <motion.div
            {...(reduce ? {} : intro(0.52, 18))}
            className="absolute bottom-[-46px] left-1/2 z-10 w-[min(600px,94%)] -translate-x-1/2 sm:bottom-[-56px]"
          >
            <HeroInterviewPreview />
          </motion.div>
        </div>
      </div>

      {/* Spacer so the bleeding mock never collides with the next section */}
      <div className="h-16 sm:h-20" />
    </section>
  );
}
