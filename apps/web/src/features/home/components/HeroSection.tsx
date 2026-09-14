"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { useT } from "@/i18n";
import { ease } from "../motion";
import { HeroInterviewPreview } from "./HeroInterviewPreview";

export function HeroSection() {
  const reduce = useReducedMotion();
  const t = useT("home");

  return (
    <section className="relative overflow-hidden">
      <div className="relative mx-auto max-w-[1320px] px-5 sm:px-6 lg:px-8 pt-14 pb-16 sm:pt-16 sm:pb-20 lg:pt-20">
        <div className="grid grid-cols-1 items-center gap-10 lg:grid-cols-12 lg:gap-8">
          {/* Left */}
          <div className="lg:col-span-6 xl:col-span-5">
            <motion.div
              initial={reduce ? false : { opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.32, ease }}
              className="inline-flex items-center gap-2 rounded-full border border-surface-border bg-surface-card px-3 py-1 shadow-xs"
            >
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--success)] opacity-50" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-[var(--success)]" />
              </span>
              <span className="text-[11px] font-medium text-ink-muted">
                {t("hero.badge")}
              </span>
            </motion.div>

            <motion.h1
              initial={reduce ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.04, ease }}
              className="mt-5 text-[clamp(2rem,4.5vw,3rem)] font-semibold leading-[1.1] tracking-[-0.02em] text-ink text-balance"
            >
              {t("hero.title")}
            </motion.h1>

            <motion.p
              initial={reduce ? false : { opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.36, delay: 0.1, ease }}
              className="mt-5 max-w-[40ch] text-[14px] sm:text-[15px] leading-[1.65] text-ink-muted"
            >
              {t("hero.desc")}
            </motion.p>

            <motion.div
              initial={reduce ? false : { opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.32, delay: 0.16, ease }}
              className="mt-7 flex flex-wrap items-center gap-2.5"
            >
              <Link href="/interview" className="btn-primary">
                {t("hero.cta.interview")}
                <ArrowRight size={14} className="btn-arrow transition-transform" />
              </Link>
              <Link href="/resume" className="btn-secondary">
                {t("hero.cta.resume")}
              </Link>
            </motion.div>
          </div>

          {/* right */}
          <motion.div
            initial={reduce ? false : { opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: 0.12, ease }}
            className="lg:col-span-6 xl:col-span-7 lg:pl-4"
          >
            <HeroInterviewPreview />
          </motion.div>
        </div>
      </div>
    </section>
  );
}
