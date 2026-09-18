"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { useT } from "@/i18n";
import { ease } from "../motion";

export function CtaSection() {
  const t = useT("home");
  const reduce = useReducedMotion();

  return (
    <section className="relative mx-auto max-w-[1200px] px-5 pb-20 pt-20 sm:px-6 sm:pb-28 sm:pt-28 lg:px-8">
      <motion.div
        initial={reduce ? false : { opacity: 0, y: 16 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, margin: "-60px" }}
        transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
        className="glass-card relative overflow-hidden p-7 sm:p-10"
      >
        {/* Brand-colored banks of light, echoing the hero */}
        <div
          className="pointer-events-none absolute inset-0 opacity-90"
          aria-hidden
          style={{
            background:
              "radial-gradient(640px 260px at 88% 0%, color-mix(in srgb, var(--primary) 16%, transparent), transparent 55%), radial-gradient(420px 200px at 6% 100%, color-mix(in srgb, var(--primary) 10%, transparent), transparent 50%)",
          }}
        />
        <div className="relative flex flex-col items-start justify-between gap-6 sm:flex-row sm:items-center">
          <div>
            <p className="page-eyebrow">{t("cta.eyebrow")}</p>
            <h2 className="mt-1.5 text-[20px] font-semibold leading-tight tracking-tight text-ink sm:text-[24px]">
              {t("cta.title")}
            </h2>
            <p className="mt-2 text-[13px] text-ink-muted">{t("cta.desc")}</p>
          </div>
          <Link href="/interview" className="btn-primary shrink-0 !h-11 !px-6 !text-[15px]">
            {t("cta.action")}
            <ArrowRight size={15} className="btn-arrow transition-transform" />
          </Link>
        </div>
      </motion.div>
    </section>
  );
}
